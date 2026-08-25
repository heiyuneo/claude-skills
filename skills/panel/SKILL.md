---
name: panel
description: 组织一次外部多模型会诊并汇总结论。用户说"会诊""外部会诊""问问外面的模型""交叉验证""让它们评评""/panel"时触发。会诊对象是 ollama cloud 上的五家非 Claude 模型；要找 opus/sonnet/fable 这些自家模型请改用 consult skill。
argument-hint: [要会诊的问题]
allowed-tools: Read, Grep, Glob, Bash
context: fork
---

就 $ARGUMENTS 组织一次外部多模型会诊。

会诊五家（都在 ollama cloud，走同一个 OpenAI 兼容端点）：
`deepseek-flash` · `nemotron` · `glm` · `kimi` · `minimax`

## 零、先判断值不值

**标准：这个决定如果错了，返工成本大不大？** 大就会诊，小就别。

不该会诊：起名字、写工具函数、任何你心里已经有答案只是想要认同的事——那样只会拿到假共识。

## 一、准备问题包

外部模型看不到本会话，也看不到代码库。**所有它们需要的东西都得亲手交过去。** 先用 Read/Grep 取出真实内容，组织成：

- 背景与技术栈（一句话）
- 目标与硬约束
- 相关代码原文（**贴全，不要省略成 `...`**）
- 会话里定过但没落盘的决定、约束、主人原话
- 三个以内的具体提问

**不要在问题包里限制答案长度**——不要写"简要回答""三句话内""控制在 500 字"。限制提问数量（三个以内）是为了让它们聚焦，限制回答长度只会让它们把论证过程砍掉，剩下光秃秃的结论，而**会诊要的恰恰是论证过程**——第三节的裁决靠的是理由硬不硬，不是结论听着顺不顺。要它们展开说透。

**不要写"我倾向于方案 A"。** 单模型咨询时说出倾向能激发反驳；多模型会诊时它会同时锚定所有模型，把假共识做实。要评审既有方案就中立标注：「以下是候选方案之一，请独立评估其代价与替代路径。」

把问题包用 Write 写到 `$D/q.md`（`$D` 见下一步）。

## 二、发出去

```bash
export NO_PROXY='ollama.com'   # 本机系统代理对 ollama.com 不通，必须绕开
[ -n "$OLLAMA_API_KEY" ] || { echo "OLLAMA_API_KEY 未设置，停"; exit 1; }
D=~/.claude/panel-runs/$(date +%Y%m%d-%H%M%S)
mkdir -p "$D/out" && echo "$D"
```

问题包写进 `$D/q.md` 之后：

```bash
cd "$D" && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -I{} sh -c 'llm -m {} --key "$OLLAMA_API_KEY" -o reasoning_effort max < q.md > out/{}.md 2> out/{}.err'
for f in out/*.err; do [ -s "$f" ] && { echo "== ${f}"; cat "$f"; }; done
wc -c out/*.md
```

五家并发，墙钟 = 最慢那家。短问题约 12 秒，贴了大段代码 + `max` 档思考的真问题按分钟计——**给 Bash 调用留足 timeout（900000）**。

**关于两个"别阉割"的设定，都已焊死，不要改回去：**

- **不传 `max_tokens`。** llm 默认就不传（请求体实测只有 `messages`/`model`/`reasoning_effort`/`stream`），端点自己按模型上限收尾，`finish_reason` 一路是 `stop` 不是 `length`。**任何时候都不要给这五家加输出长度上限**——会诊要的就是它们把话说完。
- **`-o reasoning_effort max`。** 端点接受 `none`/`low`/`medium`/`high`/`max` 五档（传非法值会报错，说明是真生效不是被无视）。实测同一道 Raft 硬题：`high` → 思考 4406 字符 / 答案 2688 字符；`max` → 思考 9667 / 答案 4180。默认档（不传）介于两者之间但不稳定。**panel 本来就只用在高赌注问题上，没有省这一档的理由。**

赶时间且问题不难时才可以临时降到 `high`；`low`/`none` 不要用在 panel 上——那样还不如不会诊。

跑完 Read 每份 `out/*.md`。**任何一家 `.err` 非空或 `.md` 为 0 字节，在汇总里明说它缺席**，不要假装五家都到齐了。

## 三、汇总（固定四段，不要省略）

1. **立场矩阵**：议题 × 各模型（同意 / 反对 / 未提及）
2. **共识区**：三家以上一致的，标高置信
3. **分歧区**：列出争点和各方理由，我给裁决和依据
4. **独有洞察**：只有一家提到但站得住的——**这一类往往最值钱**，单独列出来

**禁止按票数决策。** 这五家训练语料高度重叠，可能集体犯同一个错；孤零零的少数派意见常常才是对的。以论证质量、以及"能不能被代码或实测证伪"为准——能自己去 Read 代码核实的，就核实了再下结论。

最后给出：**我的最终建议 + 必须实测验证的点 + 存档路径 `$D`**。

## 四、可选升级：匿名互评第二轮（默认不做）

来自 Karpathy 的 llm-council Stage 2。**默认不跑**，代价约 4～9 倍 token、多一波串行延迟。

**什么时候值得跑**：五份答案平行摆着看不出高下；分歧区争的是"谁的推理更硬"而不是事实；或者赌注够大（架构拍板、上线前安全面）。

**为什么抹署名**：模型对自己家的输出风格有偏好，带署名会引入品牌偏见。

第一轮跑完、`$D` 还在的前提下：

```bash
cd "$D"
{ cat q.md
  echo; echo "---"
  echo "以下是五份对上述问题的独立作答，已抹去作者。请逐份评估**论证质量**（不是立场是否流行），排出名次并给理由；若某份提到了其他各份都没提到、且站得住的点，单独指出。"
  set -- A B C D E
  for f in out/*.md; do echo; echo "### 答案 $1"; echo; cat "$f"; shift; done
} > r2.md
mkdir -p out2 && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -I{} sh -c 'llm -m {} --key "$OLLAMA_API_KEY" -o reasoning_effort max < r2.md > out2/{}.md 2> out2/{}.err'
for f in out2/*.err; do [ -s "$f" ] && { echo "== $f"; cat "$f"; }; done
wc -c out2/*.md
```

`out/` 按字母序 = deepseek-flash / glm / kimi / minimax / nemotron，对应 A–E；**这个映射只有你和主模型知道，不要写进 `r2.md`**。

汇总时把二轮结果并进第三节的四段：被多家点名论证有洞的，即使立场是多数派也降权；被多家认可的少数派意见，提到共识区同等位置。

## 排障

```bash
# 端点/key/模型三件套是否都对（应输出一句话）
NO_PROXY='ollama.com' llm -m glm --key "$OLLAMA_API_KEY" "用一句话说说你是谁"

llm models | grep -E "deepseek-flash|nemotron|glm|kimi|minimax"   # 别名是否注册
curl -s https://ollama.com/v1/models | jq -r '.data[].id'          # 云端目录（换模型时查）
llm logs -n 5                                                      # 历史问答全在本地 SQLite
```

- 全部 401 → `$OLLAMA_API_KEY` 没读到，或 key 已轮换。
- 全部 `Connection error` → `NO_PROXY='ollama.com'` 漏了。
- 换模型/加模型：改 `~/Library/Application Support/io.datasette.llm/extra-openai-models.yaml`，再改上面命令里的名单。
