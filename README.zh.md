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

整段一起跑，最后一行会提示你粘贴 key：

```bash
# 装 llm CLI
uv tool install llm                 # 没有 uv 就用： brew install llm

# 下载两个配置文件：模型别名 + 只读仓库工具
CFG="$(dirname "$(llm logs path)")"; mkdir -p "$CFG"
for f in extra-openai-models.yaml panel_tools.py; do
  curl -fsSL "https://raw.githubusercontent.com/heiyuneo/claude-skills/main/setup/$f" -o "$CFG/$f"
done

# 存 key（会提示你粘贴，不会进 shell 历史）
llm keys set ollama
```

`llm` 会把它写进配置目录下的 `keys.json`，权限 0600。**别改用环境变量**——环境变量会被
你启动的每个子进程继承，而且所有 OpenAI 兼容模型都回退到**同一个** `OPENAI_API_KEY`，
根本没法给不同模型配不同的 key（见[混用供应商](#混用供应商)）。

跑完当场验一下，出一句话就说明 key、端点、模型三样都对了：

```bash
NO_PROXY='ollama.com' llm -m glm "用一句话说说你是谁"
```

### 3. 在 Claude Code 里装 plugin

```
/plugin marketplace add heiyuneo/claude-skills
/plugin install panel@heiyu-claude-skills
```

重开 Claude Code，说一句「会诊一下 xxx」试试。

## 混用供应商

五家没有绑死在一个供应商上。`extra-openai-models.yaml` 里**每个条目各自带** `api_base`
和 `api_key_name`，所以任何一家都能单独指到任何 OpenAI 兼容端点——厂商官方 API、网关、
本地服务、私有部署都行，其余几家原地不动。

先把新 key 存一次：

```bash
llm keys set deepseek
```

再把那一个模型指过去：

```yaml
- model_id: deepseek-flash
  model_name: deepseek-v4-flash              # 厂商自己的模型名
  api_base: "https://api.deepseek.com/v1"    # 不再走网关
  api_key_name: deepseek                     # 不再用 ollama 那个 key
  reasoning: true
```

`model_id` 是 skill 用的别名，所以改它指向哪里，**skill 一个字都不用动**。

动手前有两件事要知道：

- **绝不要在扇出命令里加 `--key`。** 显式 key 的优先级高于文件里所有 `api_key_name`，
  会**悄悄**把五家全都赶到同一个供应商上。仓里的命令是刻意不带它的。
- **思考档位各家不一样。** ollama cloud 认 `none/low/medium/high/max`；
  DeepSeek 官方认 `none/minimal/low/medium/high/xhigh/max`。两家都认 `max`（skill 发的
  就是这个），但如果某个供应商根本不认这个字段，整个调用会失败——接进来之前先手测一个。

走官方顺带是一次**诊断**：某家经过网关时不稳、直连厂商端点却稳定，那问题在网关，不在模型。

## 三个坑

1. **key 不在这个仓里，也永远不该进来。** 每人用自己的 key、自己的账。
   谁把 key 提交进来谁请客。

2. **`NO_PROXY='ollama.com'`**：skill 里的命令都带着它。没挂代理的机器上完全无害，
   别删；挂了代理而漏了它 → 全部 `Connection error`。

3. **模型名会漂。** `setup/extra-openai-models.yaml` 锁的是具体版本
   （`glm-5.3`、`kimi-k2.7-code` 等）。哪天报 model not found，查当前目录再改：

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

## 五家能查到什么

每家只有两个工具：`web_search` 和 `web_fetch`，没有别的。它们存在的理由是**查不了的
模型会编**——两场会诊里核过 6 条"实测"断言，**4 条是编的**，语气和真事实一模一样，
而且四条全是关于世界的事实（某个库的版本、某个 API 存不存在、引用的出处怎么说）。
搜索负责找到出处，抓取负责读原文那一页，而不是对着摘要推测。

`web_search` 复用你已存好的 `ollama` key，不用再申请；没有 key 时两个工具都返回
一句"不可用"，不会崩。每家最多拉 192KB 网页内容，超了工具开始拒绝。

**五家读不到你的仓库。** 能读仓的那三个工具（`list_files` / `read_file` / `grep_repo`）
上过一次线又撤了，代价是两轮实测：deny-list 被 git worktree 副本绕过（96 个被排除的
文件真的被读走）、一次静默假阴性（`pathlib.glob` 不展开 `{a,b}`，于是花 85 秒对着
明明存在的内容答"没找到"）、以及 10 次尝试 0 份可用答案。重新引入的三个条件写在
`setup/panel_tools.py` 里。**核查工具说谎比没有核查工具更糟——它给幻觉盖了"已核实"的章。**

所以送到五家手里的，就是 Claude 写进问题包的那些内容，一份不多。事后每一份都能在
`~/.claude/panel-runs/` 里翻出来看。

## 更新

推到这个仓之后，同事各自 `/plugin marketplace update heiyu-claude-skills` 就能收到。

⚠️ **`setup/` 下那两个文件不会跟着 plugin 走**——那个配置目录归 `llm` 管，不归 Claude Code。
涉及它们的更新之后，要重跑第 2 步里那段 curl。**缺了 `panel_tools.py` 会让五家一起失败**，
因为 `--functions` 加载不到文件。
