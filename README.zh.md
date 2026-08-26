# heiyu-claude-skills

自用 Claude Code skill 合集。目前一个：**panel — 外部多模型会诊**。

[English →](./README.md)

## panel — 让五个外部大模型给你会诊

平时在 Claude Code 里问问题，答你的就一个模型。但有些决定不敢只听一家的：这个模块要不要拆、这段并发代码有没有暗坑、上线前这个 PR 稳不稳。

装上它之后，你说一句「会诊一下 xxx」，它会把问题连同相关代码一起打包，**同时**甩给五个**非 Claude** 的模型（DeepSeek、Nemotron、GLM、Kimi、MiniMax），五家并发跑，然后 Claude 把五份意见收回来，整理成五段给你：

- **谁支持谁反对** —— 一张表，一眼看完（还分得出「没提到」和「想过之后否决了」）
- **大家都同意的** —— 但会标明这份一致有多少含金量（见下）
- **吵起来的地方** —— Claude 会去读你的代码，自己判谁对，并给出依据
- **只有一家提到、但确实有道理的** —— 这块往往最值钱
- **没覆盖到、没核实的** —— 哪些维度压根没问、哪些结论没人验过

四条规矩挺关键。它们存在的理由是：这里真正的危险**不是有人答错，是五家一起答错还异口同声**——那读起来像佐证，实际是给你原本的想法盖了个章。

- **不告诉那五家你倾向哪个方案**：不然它们会一起顺着你说，给你一个假共识。
- **不按票数决定**：五家训练数据高度重叠，可能一起犯同一个错，孤零零的少数派反而常常是对的。
- **共识要看它是在同意什么**：顺着你给的材料点头 = 复述，不算佐证；**反着你给的材料还一致，才是这套设计能拿到的最强信号**——因为没有任何东西在推它们往那个方向走。两者绝不写在同一个标题下。
- **来了几家决定说话的力度**：五家全到才敢把话说死，来四家就要留余地，只来三家必须明写"这份共识可能只是恰好来的这三家的巧合"。

还有两条是被具体的翻车逼出来的，**作为汇总的读者你值得知道**：

- **每条撑着结论的主张都带三选一的戳**——`verified-static`（有工件这么写）、`verified-live`（真去探过世界的状态）、`unverified`；而且**静态工件不能用来证明"发生过"**。曾经有两家报告某个数据库"已经预置了名人身份"，而仓库里能证明的只是**存在一份脚本和一条部署配方**——它们引的路径行号**全是真的**，所以两值的戳无话可说。三值把它变成**一眼可见的类型错误**，而不是"得有人记得追问一句"。
- **Claude 在发问之前先写下自己的答案，写成一份编号清单，每一条都强制变成矩阵里的一行**（标 `源：baseline`），不管五家有没有提。矩阵的行本来只从五家的答案里长出来——所以**五家全漏的那个点根本不会有行，压根不出现**。实测：五家、其中三家能读代码、加起来查了 155 次，**没有一家**注意到某系统"服务端验签、客户端不验"。加了这条之后，它会显示成**一整行"没提"**——这正是集体盲区该有的样子。

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

# 下载四个配置文件：模型别名、搜索后端、工具、体检脚本
CFG="$(dirname "$(llm logs path)")"; mkdir -p "$CFG"
for f in extra-openai-models.yaml panel_tools.py panel-doctor.py panel-search.json; do
  curl -fsSL "https://raw.githubusercontent.com/heiyuneo/claude-skills/main/setup/$f" -o "$CFG/$f"
done

# 存 key（会提示你粘贴，不会进 shell 历史）
llm keys set ollama

# 给每家设好思考档，然后看看还缺什么
python3 "$CFG/panel-doctor.py" --set-effort max
```

体检会给每家打印一行——端点、要哪把 key、这把 key 存了没、思考档是多少——缺什么就
直接给出该跑的命令。**发布的默认阵容横跨三家供应商**，所以它会告诉你还差两把 key；
下一节讲怎么办：要么去申请，要么把那两家指到你已经有 key 的地方。

`llm` 会把它写进配置目录下的 `keys.json`，权限 0600。**别改用环境变量**——环境变量会被
你启动的每个子进程继承，而且所有 OpenAI 兼容模型都回退到**同一个** `OPENAI_API_KEY`，
根本没法给不同模型配不同的 key（见[配成你自己的阵容](#配成你自己的阵容)）。

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

## 配成你自己的阵容

一家 panelist 是**三个互相独立的选择**：走哪个供应商、用哪把 key、想多深。**这三样都不在
skill 里写死。** skill 从头到尾只调五个别名：`deepseek-flash` / `nemotron` / `glm` /
`kimi` / `minimax`。每个别名指向哪儿，完全归你。

随时跑体检看现状和缺什么：

```bash
python3 "$(dirname "$(llm logs path)")/panel-doctor.py" --ping
```

```
alias           model              endpoint          key alias  stored  effort  reachable
deepseek-flash  deepseek-v4-flash  api.deepseek.com  deepseek   yes     max     ok
glm             glm-5.3            open.bigmodel.cn  zhipu      NO      unset   skipped
...
```

### 供应商和 key

`extra-openai-models.yaml` 里每一条都自带 `api_base` 和 `api_key_name`，所以任何一家都能
指到任何 OpenAI 兼容的端点——厂商官方 API、网关、本地服务、私有部署都行，其余四家不受
影响。改三行就搬一家：

```yaml
- model_id: deepseek-flash                   # skill 认的就是这个，别改
  model_name: deepseek-v4-flash              # 那个供应商自己的型号名
  api_base: "https://api.deepseek.com/v1"    # 换掉网关
  api_key_name: deepseek                     # 换掉 ollama
  reasoning: true                            # 必须有，否则思考档根本设不了
```

然后把那把 key 存一次：`llm keys set deepseek`。

**不想为某一家专门去注册账号？** 把它指到你已经在用的供应商就行。**五家全挂在 Ollama
上、只用一把 key，也是一个完全成立的会诊**——你损失的是一两个模型版本，不是这套设计。
这五个别名是**五个位子，不是五家厂商**。

### 每家想多深

思考档存在 `llm` 自己的配置里，**不由 skill 传**：

```bash
llm models options set glm reasoning_effort max
llm models options show glm
python3 "$(dirname "$(llm logs path)")/panel-doctor.py" --set-effort max   # 五家一次设完
```

**档位数各家不一样。** Ollama 网关是 `none/low/medium/high/max` 五档；DeepSeek 官方端还多
`minimal` 和 `xhigh`。两边都认 `max`。**传了对方不认的字段会让整个调用失败**，所以搬完一家
之后先手动试一次。

⚠️ **这里唯一会闷声出事的，就是思考档没设。** 它不报错——模型只是跑在服务端自己挑的档位
上，答案看起来**完全正常**。所以 skill 宁可**拒绝启动**也不让这种情况发生，`--set-effort max`
一条命令就能清掉。这也正是 skill **不再硬编码** `-o reasoning_effort max` 的原因：命令行上
的显式参数会盖掉所有存好的默认值，上面这一整节就全废了。

### 搜索用哪家

`web_search` 会**按顺序**走一张后端表，谁先查到就用谁的。这张表放在 `panel-search.json`，
跟模型表并排——**理由完全一样：搜索用哪家是配置，不该写死在代码里**。

```json
{
  "name": "brave",                       // 答案开头会标 "(index: brave)"
  "key": "brave",                        // 用哪把存好的 llm key
  "url": "https://api.search.brave.com/res/v1/web/search?extra_snippets=true&q={q}",
  "header": { "X-Subscription-Token": "{key}" },
  "results": "web.results",              // 结果数组在 JSON 里的点路径
  "title": "title", "link": "url",       // 哪个字段是标题、哪个是链接
  "content": ["description", "extra_snippets"]   // 拼成摘要的字段
}
```

POST 型的 API 也支持——加 `"method": "POST"` 和一个 `"body"`，`{q}` 和 `{key}` 在两边都会
被替换。**任何返回"标题+链接+一段文字"的 JSON 数组的搜索服务，八行就能接进来。**

**没存 key 的后端会被静默跳过**，所以你可以把条目当模板留在文件里，存了 key 才激活。
默认发的是 Brave 在前、Ollama 在后；`panel-doctor.py` 会打印当前生效的顺序，答案里也会标
最后是哪家答的。

为什么要不止一个：**一个索引查不到，不等于不存在。** 所有配好的后端都查空时，工具会**明说
"都搜过了，都是空的"**，这样答题方永远没法把沉默说成"这东西不存在"。**这才是第二个索引值一把
key 的理由**——不是因为哪家索引更可信。

### 两件值得先知道的

- **绝不要在扇出命令上加 `--key`。** 它会一次性盖掉所有条目的 `api_key_name`，却**不动各自
  的 `api_base`**——于是同一把钥匙被递到好几家门口，没签发过它的那几家直接回 `401`。发布的
  命令刻意不用它。
- **直连官方端本身就是一种诊断。** 某一家在网关上不稳、换到厂商自己的端点就稳，那问题在
  网关，不在模型。

## 三个坑

1. **key 不在这个仓里，也永远不该进来。** 每人用自己的 key、自己的账。
   谁把 key 提交进来谁请客。

2. **`NO_PROXY='ollama.com'`**：skill 里的命令都带着它。没挂代理的机器上完全无害，
   别删；挂了代理而漏了它 → 全部 `Connection error`。

3. **模型名会漂。** `setup/extra-openai-models.yaml` 锁的是具体版本
   （`glm-5.3`、`kimi-k3` 等）。哪天报 model not found，查当前目录再改：

   ```bash
   curl -s https://ollama.com/v1/models | jq -r '.data[].id'
   ```

## 排障

| 症状 | 原因 |
|---|---|
| 全部 401 | key 没用 `llm keys set` 存进去，或已轮换 |
| 全部 `Connection error` | 漏了 `NO_PROXY='ollama.com'` |
| 全部瞬间失败 | `panel_tools.py` 没放进 llm 配置目录，`--functions` 加载不到 |
| 某一家沉默很久后突然消失 | 它撞到了 `--cl` 链上限——那是保险丝，撞上直接掐断整个调用 |
| model not found | 模型名漂了，见坑 3 |

```bash
llm models | grep -E "deepseek-flash|nemotron|glm|kimi|minimax"   # 别名注册上没
llm keys list                                                     # 存了哪几把 key
llm logs -n 5                                                     # 历史问答都在本地 SQLite
```

## 五家能查到什么

每家五个工具，没有别的。

**查外面的世界** —— `web_search` / `web_fetch`。它们存在的理由是**查不了的模型会编**：
两场会诊里核过 6 条"实测"断言，**4 条是编的**，语气和真事实一模一样，而且四条全是关于
世界的事实（某个库的版本、某个 API 存不存在、引用的出处怎么说）。搜索负责找到出处，
抓取负责读原文那一页，而不是对着摘要推测。

`web_search` 可以查**两个互相独立的索引**：存一把 `brave` key，它就先查 Brave，出错或空
结果自动回落 Ollama，每条结果都标明是哪个索引答的。这不是说哪家有偏见，是**覆盖率**——
一个索引查不到不等于不存在；两个都查过还是空，工具会明说"都搜过了，都是空的"，
**绝不让沉默被读成"不存在"**。不配这把 key 也能跑，搜索直接走 Ollama。`web_fetch` 永远
留在 Ollama 那边，因为 Brave 只给摘要不给正文。

**查你的仓库** —— `list_files` / `read_file` / `grep_repo`，范围限定在发起会诊的那个仓。
没有它们的话，问题包就是五家能看到的全部——**等于一个人决定了五个模型眼里的整个世界**，
而这个人恰好也是最后做裁决的那个。

这三个工具**上过一次线又撤了，现在是重建不是恢复**，因为当初那两次失败教训不一样：

- 用来挡秘密的黑名单，被一份 `.worktrees/` 的副本绕了过去。修法不是换个更好的模式表，
  而是**根本不要模式表**：现在可见范围由 `git ls-files` **正向定义**，没进版本控制的东西
  对这些工具**根本不存在**——`.env`、密钥、构建产物、游离的副本天然够不着，没有规则要
  维护，也就没有规则会设错。
- 搜索用 `pathlib.glob` 实现，而它不展开 `{a,b}`，于是花 85 秒对着**明明存在**的内容答
  "没找到"。**这条才是绝不能重犯的**：报假阴性的工具比没有工具更糟——模型接着就会用
  "我查过了"的口气断言不存在，**你的核查环节反倒成了生产幻觉的那一环**。现在底座是
  `git grep`，花括号在交给 git 之前先展开，每个空结果都必须说"搜过了，是空的"，
  `setup/panel_tools.py` 里带着专测这条回归的自检。

每家最多拉 192KB 网页内容、512KB 仓库内容，超了工具开始拒绝，并会告诉模型
"用你手上有的回答，并说明哪些点没核实"。

送到五家手里的东西、五份原始回答、Claude 在**发出问题之前**写下的自己那份答案、以及最后
的汇总，全部存在 `~/.claude/panel-runs/` 下——所以你随时能拿"五家实际说了什么"去对
"汇总声称它们说了什么"。验收某一次跑：

```bash
CHECK=$(find ~/.claude/skills ~/.claude/plugins/cache -name check-run.sh -path '*panel*' 2>/dev/null | head -1)
sh "$CHECK"
```

## 各家的已知脾气

装之前知道一下，省得误判：

| 别名 | 表现 |
|---|---|
| `kimi` | 最稳的一条腿，也是五家里工具用得最深的。它对本仓做过的一条 `grep_repo` 断言，复核下来**逐字逐行全对**；而且不用提醒就自己标了「这条实查过 / 这条只是二手转述、我没再追」 |
| `deepseek-flash` | 偶尔跑飞撞上端点自己的 token 上限，超时闸兜得住 |
| `nemotron` | 不是挂，是慢——两次被砍的文件里都还留着 22–25KB 的真答案 |
| `minimax` | **单独关掉工具**。它在三次大包会诊里都崩了，但诊断**不是**"工具调用坏"——单次搜索在各个思考档位都是几秒钟就过。真正复现出来的是**不收敛**：让它查四件事，它会拿几乎相同的词反复重搜。关掉工具反而两次交出全场最长的答案，而且它成了唯一**纯靠问题包推理**的对照组 |
| `glm` | 偶尔首次请求卡死在零字节，此时**立刻重跑会撞 429**——被丢弃的那笔请求还占着账户的并发位。skill 里已改成等一会儿再补跑掉队的 |

## 更新

推到这个仓之后，同事各自 `/plugin marketplace update heiyu-claude-skills` 就能收到。

⚠️ **`setup/` 下那四个文件不会跟着 plugin 走**——那个配置目录归 `llm` 管，不归 Claude Code。
涉及它们的更新之后，要重跑第 2 步里那段 curl，再跑一次 `panel-doctor.py` 确认。**缺了 `panel_tools.py` 会让五家一起失败**，
因为 `--functions` 加载不到文件。
