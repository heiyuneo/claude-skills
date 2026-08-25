# heiyu-claude-skills

自用 Claude Code skill 合集。目前一个：**panel — 外部多模型会诊**。

[English →](./README.md)

## panel — 让五个外部大模型给你会诊

平时在 Claude Code 里问问题，答你的就一个模型。但有些决定不敢只听一家的：这个模块要不要拆、这段并发代码有没有暗坑、上线前这个 PR 稳不稳。

装上它之后，你说一句「会诊一下 xxx」，它会把问题连同相关代码一起打包，**同时**甩给五个**非 Claude** 的模型（DeepSeek、Nemotron、GLM、Kimi、MiniMax），五家并发跑，然后 Claude 把五份意见收回来，整理成四段给你：

- **谁支持谁反对** —— 一张表，一眼看完
- **大家都同意的** —— 这部分基本可以放心
- **吵起来的地方** —— Claude 会去读你的代码，自己判谁对
- **只有一家提到、但确实有道理的** —— 这块往往最值钱

有两条规矩挺关键：**不告诉那五家你倾向哪个方案**（不然它们会一起顺着你说，给你一个假共识）；**不按票数决定**（五家训练数据高度重叠，可能一起犯同一个错，孤零零的少数派反而常常是对的）。

### 什么时候别用

起名字、写个工具函数、你心里其实已经有答案只是想找人点个头 —— 这些不值。

判断标准就一句：**这事要是搞错了，返工成本大不大？** 大就会诊，小就算了。

一次两三分钟（五家在慢慢想，思考档拉满了），花几毛到几块钱。

### 怎么用

```
/panel 这个订单状态机要不要拆成独立服务
会诊一下 src/sync/ 这段并发写入，有没有我没看到的竞态
```

## 装（两分钟，三步）

### 1. 先拿一个 Ollama key

打开 <https://ollama.com/settings/keys>，登录后点 **Create key**，复制出来备用。

⚠️ **必须用你自己的 key。** ollama 是按量计费的，谁的 key 谁付钱，别问别人要。

### 2. 复制这一整段贴进终端

把最后一行的 `把你的key贴这里` 换成上一步复制的 key，然后整段一起跑：

```bash
# 装 llm CLI
uv tool install llm                 # 没有 uv 就用： brew install llm

# 下载模型别名配置（告诉 llm 那五个模型叫什么、去哪找）
mkdir -p "$(dirname "$(llm logs path)")"
curl -fsSL https://raw.githubusercontent.com/heiyuneo/claude-skills/main/setup/extra-openai-models.yaml \
  -o "$(dirname "$(llm logs path)")/extra-openai-models.yaml"

# 存 key
echo 'export OLLAMA_API_KEY=把你的key贴这里' >> ~/.zshenv && chmod 600 ~/.zshenv
source ~/.zshenv
```

⚠️ **key 要写进 `.zshenv`，不是 `.zshrc`。** Claude Code 每次执行命令都新开一个非交互
shell，而 zsh 非交互模式只读 `.zshenv`。写进 `.zshrc` 的症状特别阴：你在终端里手敲验证
命令能通，但 skill 一跑就报 `OLLAMA_API_KEY 未设置` 然后停——很容易查半天。

跑完当场验一下，出一句话就说明 key、端点、模型三样都对了：

```bash
NO_PROXY='ollama.com' llm -m glm --key "$OLLAMA_API_KEY" "用一句话说说你是谁"
```

### 3. 在 Claude Code 里装 plugin

```
/plugin marketplace add heiyuneo/claude-skills
/plugin install panel@heiyu-claude-skills
```

重开 Claude Code，说一句「会诊一下 xxx」试试。

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
