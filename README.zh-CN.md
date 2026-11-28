# Chat Input Contract

在怀疑模型之前，先核对它实际收到的 token。

这是离线的聊天预处理契约验收工具：捕获本地 tokenizer、聊天模板和调用选项的真实输出，比较消息、渲染文本、词表身份、分词与特殊 token 后处理的差异。不是新分词算法，不评测模型质量，也不保证真实部署服务与本地路径完全一致。

## 一条命令复现真实错误

在源码目录，使用 Python 3.11+：

```sh
python -m pip install ".[capture]"
chat-input-contract demo --out demo-output
```

实际演示结果：`safe=match, broken=drift, cases=3`。打开 `demo-output/broken-report.html` 查看证据。模板已添加 BOS/EOS，后续分词再次添加它们，会产生真实的 token 序列变化；修复路径关闭额外添加并重新执行，必须恢复一致。演示使用自制小词表和真实库调用，不需要模型权重、GPU、API key 或联网推理。

## v0.2：一条命令检查当前配置

首次人工审核并保存基线后，不再需要手动保存候选快照：

```sh
chat-input-contract check manifest.json --baseline baseline.json
chat-input-contract check manifest.json --baseline baseline.json --json check.json --html check.html
```

第一条默认不写文件，第二条显式保存报告；均不会自动修改或接受新基线。报告会定位最早观测到的变化，区分首尾插入，并对大范围差异和截断明确标注。终端只显示用例序号、阶段与位置，不打印消息或token。

`check`使用解释版报告v2；原`compare`默认仍为v1，加`--explain`才输出v2。真实0.1.0快照保持可读。v2的`--include-content`只导出有界差异预览，仍须按敏感数据处理。

采集预检与执行绑定同一份输入字节，避免重复读取造成保护清单错位。原生分词器在子进程内运行，异常日志不向外泄露；60秒超时会拒绝本次采集。这不是恶意代码沙箱或硬内存隔离。观测到两条采集路线不一致时直接拒绝，不冒称后处理错误；稳定的一次观测不证明模板永远确定。

## 用自己的文件验收

按 [英文 README](README.md#capture-your-configuration) 创建 JSON 清单，明确本地 tokenizer.json、chat.jinja、特殊 token、消息用例和调用选项。不要把示例的 token 名字当所有模型的默认值。

```sh
chat-input-contract capture manifest.json --out baseline.json
# 修改配置后，再采集一次
chat-input-contract capture manifest.json --out candidate.json
chat-input-contract compare baseline.json candidate.json --json result.json --html result.html
```

退出码：0=可比较且一致；1=发现漂移；2=不可比较、输入拒绝或执行失败。缺少用例不会按共有部分偷偷判通过；词表变化即使暂未改变示例中的整数 ID，也会报告。模型升级导致的有意差异需要人工审核，不会自动改配置或接受新基线。

## 隐私与边界

快照包含渲染后的消息和可还原文本的 token 信息，应视为敏感文件。默认 JSON/HTML 比较报告隐藏原文、ID 与 token 拼写；仍保留用例名、长度、指纹和版本配置，分享前检查。只有显式 `--include-content` 才把完整内容加入比较报告。工具不上传、不遥测、不引用外部网页资源；输出默认禁止覆盖，`--force` 也不能覆盖输入文件。

首版实测捕获集成为 Transformers 5.8.0 + tokenizers 0.22.2 + Jinja2 3.1.6；比较已存快照不依赖它们。只支持显式本地 fast tokenizer JSON 和文本消息；不支持自动模型发现、慢分词器、自定义 Python 类、多模态、工具调用、实时 vLLM/llama.cpp 服务或模型质量判断。可信本地模板不是恶意代码安全沙箱，预算限制不是硬内存/时间隔离。

```sh
python -m unittest discover -s tests -v
```

[精确契约](docs/SPEC.md) · [验收记录](docs/VERIFICATION.md) · [依赖许可](docs/DEPENDENCIES.md)

欢迎提交自制的最小复现与脱敏报告；不要提交私人对话、密钥或未获授权的数据。原始代码采用 MIT 许可。

## 快速开始与支持状态

### 问题
通过分离渲染文本、分词、词表和特殊 token 后处理证据，捕获聊天预处理漂移。

### 安装
```sh
python -m pip install ".[capture]"
```

### 成功命令
```sh
chat-input-contract demo --out demo-output
```
预期：真实安全路径匹配，损坏路径被识别为 drift；退出码 0。

### 故意失败命令
```sh
chat-input-contract compare demo-output/direct-snapshot.json demo-output/broken-snapshot.json --json drift.json --html drift.html
```
预期：重复特殊 token 路径被报告为 drift；退出码 1。

### 证据与覆盖边界
证据使用原创本地 fixture 和真实 Transformers/tokenizers 调用、严格输入与覆盖检查、重复特殊 token 漂移及修复、输出保护、隐私行为、HTML 转义和内存变异对照。覆盖范围是声明的本地 fast-tokenizer/文本消息子集，不是模型推理或在线服务一致性。

### 支持状态
版本 0.2.0 支持 Python 3.11+。采集固定使用 Transformers 5.8.0、tokenizers 0.22.2 和 Jinja2 3.1.6；不隐式认证更新版本。已保存快照对比无第三方运行时依赖。维护为尽力而为，不提供 SLA。

### 限制
不支持 AutoTokenizer 发现、自定义/慢速 tokenizer、多模态/工具输入、任意模板参数、批处理/填充/截断、在线 vLLM/llama.cpp 一致性或模型质量评估。快照包含敏感的渲染提示词和可逆 token 信息。
