# heiyu-claude-skills

自用 Claude Code skill 合集。目前一个：**panel — 外部多模型会诊**。

[English →](./README.en.md)

## panel 是什么

在 Claude Code 里说「会诊」「外部会诊」「问问外面的模型」「交叉验证」或直接 `/panel`，
它会把你的问题打成问题包，同时发给 ollama cloud 上的五家**非 Claude** 模型
（`deepseek-flash` · `nemotron` · `glm` · `kimi` · `minimax`），
五家并发跑满思考档，回来汇总成固定四段：立场矩阵 / 共识区 / 分歧区 / 独有洞察。

用在**返工成本大**的决定上：架构拍板、上线前的安全面、选型。
起名字、写工具函数、心里已经有答案只想找认同的事——别用，那只会拿到假共识。

## 装

### 1. 装 `llm` CLI

```bash
uv tool install llm      # 或： pipx install llm     # 或： brew install llm
```

### 2. 加这个 marketplace 并装 plugin

在 Claude Code 里：

```
/plugin marketplace add heiyuneo/claude-skills
/plugin install panel@heiyu-claude-skills
```

### 3. 放模型别名配置

```bash
git clone https://github.com/heiyuneo/claude-skills.git /tmp/claude-skills
cp /tmp/claude-skills/setup/extra-openai-models.yaml "$(dirname "$(llm logs path)")/"
```

（这一步没法跟着 plugin 走——`llm` 的配置目录不归 Claude Code 管。）

### 4. 各自申请自己的 key

去 <https://ollama.com> 注册拿 key，**按量计费，走各人自己的账**：

```bash
echo 'export OLLAMA_API_KEY=你自己的key' >> ~/.zshenv && chmod 600 ~/.zshenv
```

⚠️ **是 `.zshenv`，不是 `.zshrc`。** Claude Code 每次执行命令都新开一个非交互 shell，
而 zsh 非交互模式只读 `.zshenv`。写进 `.zshrc` 的话，你在终端里手敲验证命令会通，
但 skill 一跑就报 `OLLAMA_API_KEY 未设置` 然后停——很容易查半天。

### 5. 验

```bash
NO_PROXY='ollama.com' llm -m glm --key "$OLLAMA_API_KEY" "用一句话说说你是谁"
```

出一句话就成了。重开 Claude Code，说「会诊」试试。

## 三个坑

1. **key 不在这个仓里，也永远不该进来。** 每人用自己的 key、自己的账。
   谁把 key 提交进来谁请客。

2. **`NO_PROXY='ollama.com'`**：skill 里的命令都带着它。没挂代理的机器上完全无害，
   别删；挂了代理而漏了它 → 全部 `Connection error`。

3. **模型名会漂。** `setup/extra-openai-models.yaml` 锁的是具体版本
   （`glm-5.2`、`kimi-k2.7-code` 等）。哪天报 model not found，查当前目录再改：

   ```bash
   curl -s https://ollama.com/v1/models | jq -r '.data[].id'
   ```

## 排障

| 症状 | 原因 |
|---|---|
| 全部 401 | key 没读到，或已轮换 |
| 全部 `Connection error` | 漏了 `NO_PROXY='ollama.com'` |
| model not found | 模型名漂了，见坑 3 |

```bash
llm models | grep -E "deepseek-flash|nemotron|glm|kimi|minimax"   # 别名注册上没
llm logs -n 5                                                     # 历史问答都在本地 SQLite
```

## 更新

推到这个仓之后，同事各自 `/plugin marketplace update heiyu-claude-skills` 就能收到。
