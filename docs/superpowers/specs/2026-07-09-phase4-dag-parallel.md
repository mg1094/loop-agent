# Phase 4 — DAG + Parallel Execution 设计

> **Goal:** 让 `Supervisor` 从线性串行 workflow 升级为 DAG（有向无环图）调度，支持同层节点并行执行。
> **Scope:** 支持多标的并行调研等 fan-out / fan-in 场景。
> **Backward compat:** Phase 3 的 `Supervisor(workers, workflow)` 调用方式继续工作，9 个现有 `test_supervisor.py` 测试保持不变。

---

## 1. 核心数据模型

### 1.1 已有模型（Phase 3 不变）

```python
@dataclass
class WorkerSpec:
    name: str
    tools: List[str]
    skills: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    max_iterations: int = 30
```

### 1.2 新增 `StepTemplate`

`StepTemplate` 描述一个 step 的"模板"：哪个 worker 跑、任务模板长什么样。没有运行时状态。

```python
@dataclass
class StepTemplate:
    """模板：声明一个 step 的形状（worker + 任务模板）。无运行时状态。

    对应 Phase 3 的 ``WorkflowStep``，但要求显式 ``id``。
    """

    id: str
    worker: str
    task_template: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("StepTemplate.id must be a non-empty string")
        if not isinstance(self.worker, str) or not self.worker.strip():
            raise ValueError("StepTemplate.worker must be a non-empty string")
        if not isinstance(self.task_template, str):
            raise ValueError("StepTemplate.task_template must be a string")
```

### 1.3 新增 `StepInstance`

`StepInstance` 是 DAG 的一个运行时节点，引用一个 `StepTemplate`，并带有自己的 `user_vars` 和依赖关系。

```python
@dataclass
class StepInstance:
    """运行时实例：模板的具体执行。

    每个 instance 是 DAG 的一个节点；``depends_on`` 引用其他
    ``StepInstance.id``。
    """

    id: str
    step: str
    user_vars: Dict[str, str] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("StepInstance.id must be a non-empty string")
        if not isinstance(self.step, str) or not self.step.strip():
            raise ValueError("StepInstance.step must reference a StepTemplate.id")
        if not isinstance(self.user_vars, dict):
            raise ValueError("StepInstance.user_vars must be a dict")
        if not isinstance(self.depends_on, list):
            raise ValueError("StepInstance.depends_on must be a list")
```

### 1.4 Fan-out helper

```python
def expand_fanout(
    step: str,
    items: List[Dict[str, str]],
    id_prefix: str,
) -> List[StepInstance]:
    """把 ``items`` 列表展开成 N 个 StepInstance（1:1 fan-out）。"""
    if not isinstance(step, str) or not step.strip():
        raise ValueError("expand_fanout step must be a non-empty string")
    if not isinstance(id_prefix, str) or not id_prefix.strip():
        raise ValueError("expand_fanout id_prefix must be a non-empty string")
    if not isinstance(items, list):
        raise ValueError("expand_fanout items must be a list")
    return [
        StepInstance(
            id=f"{id_prefix}_{i}",
            step=step,
            user_vars=item,
        )
        for i, item in enumerate(items)
    ]
```

---

## 2. Supervisor 构造签名

Phase 4 的 `Supervisor` 接受 `templates` + `instances`，同时保留 Phase 3 的 `workflow` 作为 backward-compat shim。

```python
class Supervisor:
    def __init__(
        self,
        llm: Optional[ChatLLM] = None,
        session_store: Optional[SessionStore] = None,
        workers: Optional[List[WorkerSpec]] = None,
        templates: Optional[List[StepTemplate]] = None,
        instances: Optional[List[StepInstance]] = None,
        workflow: Optional[List[WorkflowStep]] = None,   # Phase 3 backward compat
        max_parallel: int = 4,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> None:
        ...
```

### 2.1 参数约束

| 组合 | 行为 |
|---|---|
| `workflow` 非空 | 自动转换为 `templates` + `instances`（线性链）。 `templates` 和 `instances` 必须为空。 |
| `templates` + `instances` 非空 | 走 DAG 模式。`workflow` 必须为空。 |
| 只传 `workers`（无任何编排参数） | 使用默认的 research → writer `templates` + `instances`，与 Phase 3 默认行为一致。 |
| `workflow` 和 `templates/instances` 同时非空 | `ValueError` |
| `instances` 非空但 `templates` 为空 | `ValueError` |
| `templates` 非空但 `instances` 为空 | `ValueError`（空 DAG 无意义） |

### 2.2 `workflow` 到 DAG 的转换规则

```python
# Phase 3 调用
Supervisor(workers=[...], workflow=[
    WorkflowStep(worker="research", task_template="...{task}..."),
    WorkflowStep(worker="writer", task_template="...{prev_output}..."),
])

# 内部映射为
# templates = [
#     StepTemplate(id="_step_0", worker="research", task_template="...{task}..."),
#     StepTemplate(id="_step_1", worker="writer", task_template="...{prev_output}..."),
# ]
# instances = [
#     StepInstance(id="_step_0_inst", step="_step_0"),
#     StepInstance(id="_step_1_inst", step="_step_1", depends_on=["_step_0_inst"]),
# ]
```

---

## 3. DAG 验证（构造时 fail-fast）

`Supervisor.__init__` 构造时校验：

1. **模板 id 唯一**：重复 `StepTemplate.id` → `ValueError`
2. **实例 id 唯一**：重复 `StepInstance.id` → `ValueError`
3. **实例引用的 step 存在**：`instance.step` 不在 `template_by_id` 中 → `ValueError`
4. **实例引用的依赖存在**：`dep_id` 不在 `instance_by_id` 中 → `ValueError`
5. **无循环依赖**：Kahn 或 DFS 检测 → `ValueError("cycle detected: ...")`

---

## 4. 执行模型

### 4.1 拓扑分层

使用 Kahn 算法把 `instances` 分层：`[[layer0_nodes], [layer1_nodes], ...]`。

- 入度为 0 的节点在第 0 层。
- 每完成一层，解除下一层入度；入度归零的进入下一层。

### 4.2 同层并行

同一层内所有 `StepInstance` 用 `ThreadPoolExecutor(max_workers=self._max_parallel)` 并行执行。

`AgentLoop` 是同步的，所以用 `executor.submit(...)` + `as_completed(...)`。

### 4.3 跨层串行

第 N 层全部完成后，才启动第 N+1 层。

### 4.4 模板渲染

渲染 `StepInstance` 对应的 `StepTemplate.task_template` 时，上下文 `ctx` 包含：

1. `task`：用户传入的原始 task 字符串。
2. `user_vars`：当前 `StepInstance.user_vars` 的键值对。
3. `prev_output`：当 `depends_on` 长度为 1 时，等于该上游 `content` 字符串；否则不可用（渲染会触发 `SupervisorConfigError`）。
4. `{dep_id}`：每个依赖实例的 `content`，以依赖 id 作为键。

渲染失败时抛 `SupervisorConfigError`（沿用 Phase 3 的异常类型）。

### 4.5 失败处理

| 场景 | 行为 |
|---|---|
| 同层某个 instance 失败 | 同层其他 instance 继续；该层标记为 partial；DAG 仍继续到下一层。 |
| 同层所有 instance 失败 | 同上，aggregate status 为 partial。 |
| 下游 instance 的依赖中有失败的上游 | 仍执行，但失败的 `{dep_id}` 渲染为占位字符串 `"[upstream failed: <id>]"`。 |
| 运行时取消 | `ThreadPoolExecutor.shutdown(wait=False, cancel_futures=True)`，已提交的 future 跑完。 |

### 4.6 Final output

`Supervisor.run()` 返回的 `content` 取拓扑最深一层的第一个 instance 的 output。

如果希望显式指定最终输出 instance，未来可扩展 `output_instance_id` 参数；Phase 4 不引入。

---

## 5. 事件

沿用并扩展 Phase 3 事件：

| Event | 触发时机 |
|---|---|
| `workflow_layer_start` | 一个拓扑层开始执行 |
| `workflow_layer_end` | 一个拓扑层全部完成 |
| `workflow_step_start` | 单个 instance 开始执行 |
| `workflow_step_end` | 单个 instance 执行完成 |
| `supervisor_step_warning` | 单个 instance 返回非 success 状态 |

---

## 6. 示例用法

### 6.1 多标的并行调研（fan-out / fan-in）

```python
from loop_agent.orchestration import Supervisor, WorkerSpec, StepTemplate, StepInstance, expand_fanout

sup = Supervisor(
    workers=[
        WorkerSpec("scout", tools=["web_search"]),
        WorkerSpec("analyst", tools=["read_file"]),
        WorkerSpec("writer", tools=["write_file"]),
    ],
    templates=[
        StepTemplate(id="scout", worker="scout", task_template="查 {symbol} 最新动态：{task}"),
        StepTemplate(id="analyze", worker="analyst", task_template="分析：{prev_output}"),
        StepTemplate(id="merge", worker="writer", task_template="""
合并三份分析：
AAPL: {s_AAPL}
GOOG: {s_GOOG}
MSFT: {s_MSFT}
"""),
    ],
    instances=[
        *expand_fanout("scout", [
            {"symbol": "AAPL"}, {"symbol": "GOOG"}, {"symbol": "MSFT"},
        ], id_prefix="s"),
        StepInstance(id="a_AAPL", step="analyze", depends_on=["s_0"]),
        StepInstance(id="a_GOOG", step="analyze", depends_on=["s_1"]),
        StepInstance(id="a_MSFT", step="analyze", depends_on=["s_2"]),
        StepInstance(id="merge", step="merge", depends_on=["a_AAPL", "a_GOOG", "a_MSFT"]),
    ],
)

result = sup.run("请生成一份美股调研报告")
```

### 6.2 Phase 3 backward compat

```python
# 继续工作，内部自动转 DAG
sup = Supervisor(
    llm=llm,
    session_store=store,
    workflow=[
        WorkflowStep(worker="research", task_template="查 {task}"),
        WorkflowStep(worker="writer", task_template="写报告：{prev_output}"),
    ],
)
```

---

## 7. 测试覆盖

| 测试文件 | 数量 | 覆盖点 |
|---|---|---|
| `tests/test_step_template.py` | 4 | 字段默认值、id 校验、worker 校验、task_template 类型校验 |
| `tests/test_step_instance.py` | 4 | 字段默认值、id 校验、step 引用校验、depends_on 类型校验 |
| `tests/test_expand_fanout.py` | 3 | 正常展开、空 list、id_prefix 边界 |
| `tests/test_dag_validation.py` | 6 | 循环检测、未知 step、未知 dep、重复 id、空 instances、未知 worker |
| `tests/test_supervisor_dag.py` | 8 | 拓扑分层、并行执行、单层失败、prev_output 简写、多依赖 dep_id 渲染、错误占位符、事件顺序、max_parallel 限制 |
| `tests/test_supervisor.py` | (existing) | Phase 3 backward compat 保持通过 |

目标测试数：108 → 130+ 通过。

---

## 8. 文件变更

### 新增文件
- `loop_agent/orchestration/dag.py` — Kahn 分层 + 拓扑校验
- `tests/test_step_template.py`
- `tests/test_step_instance.py`
- `tests/test_expand_fanout.py`
- `tests/test_dag_validation.py`
- `tests/test_supervisor_dag.py`

### 修改文件
- `loop_agent/orchestration/specs.py` — 新增 `StepTemplate` / `StepInstance` / `expand_fanout`
- `loop_agent/orchestration/supervisor.py` — 支持 `templates` / `instances` / `workflow` shim / DAG 执行
- `loop_agent/orchestration/__init__.py` — re-export 新类型
- `README.md` — 更新测试徽章
- `docs/superpowers/sdd/progress.md` — 记录 Phase 4 状态

---

## 9. 非目标（Phase 4 不做）

- **条件分支 / if-else 执行**：所有 DAG 边在构造时确定。
- **动态生成 instance**：`expand_fanout` 是构造期 helper，不支持 run-time 动态发现。
- **重试 / timeout per instance**：worker 自己的 `max_iterations` 是 ReAct 上限；instance 级别重试不在范围。
- **跨层结果聚合函数**：`merge` step 自己负责用模板把上游结果拼起来，不内置 join 策略。
- **YAML 加载器**：保持纯 Python 配置；YAML 入口是潜在 Phase 5。
