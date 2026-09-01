#!/bin/sh
# 验收一次 panel 跑：产物是否齐、baseline 时序是否可证、五家出席情况。
# 用法：sh ~/.claude/skills/panel/check-run.sh [归档目录]   （省略则取最近一次）
# ⚠️ 归档目录是全机共享的（~/.claude/panel-runs/），不按项目或会话分。多个线程/会话并行时
#    「最近一次」很可能是别人的跑。**永远显式传 $D**，省略只在你确定只有你一个人在跑时才安全。
D="${1:-$(ls -dt ~/.claude/panel-runs/*/ 2>/dev/null | head -1)}"
case "$D" in */) ;; *) D="$D/";; esac
[ -d "$D" ] || { echo "找不到归档目录"; exit 1; }
echo "归档: $D"

# 「还在跑」和「已经死了」从外面长得一模一样：慢的那家在工具循环里只发工具调用，落盘 0 字节，
# 三份写完的答卷躺着不动 —— 实测有人据此判定整场被遗弃，而它当时还在跑。先把这条说清楚。
if [ -f "$D/.fanout_done" ] && [ -f "$D/.fanout_started" ]; then
  echo "✅ 扇出已完成    用时 $(( ($(cat "$D/.fanout_done") - $(cat "$D/.fanout_started")) / 60 )) 分钟"
elif [ -f "$D/.fanout_started" ]; then
  el=$(( $(date +%s) - $(cat "$D/.fanout_started") ))
  if   [ -f "$D/summary.md" ]; then :   # 出了汇总就是跑完了，标记是本版才加的，旧归档没有
  elif [ "$el" -gt 3600 ]; then echo "ℹ️  无完成标记，但已过 $((el/3600)) 小时 —— 旧归档（本版之前的跑不写标记）"
  else
    echo "⏳ 扇出未标记完成 —— 已 $((el/60))分$((el%60))秒。单家上限 720s，带一次重试最长约 1470s(24分)。"
    [ "$el" -lt 1500 ] && echo "   还在预算内，**别当成挂了**；下面的出席是中途快照。" \
                       || echo "   已超预算 —— 要么 fork 没照抄扇出块(自己串行补跑)，要么整场被遗弃。"
  fi
fi
echo

[ -f "$D/q.md" ] && echo "✅ q.md          $(wc -c < "$D/q.md" | tr -d ' ')B" || echo "❌ q.md 缺失"

# 污染边界是「五家的答案」，不是问题包 —— baseline 晚于 q.md 是正常的（skill 就是
# 这么排的：先建包，再写 baseline，再发出去）。所以拿最早那份答案当界。
if [ -f "$D/baseline.md" ]; then
  b=$(stat -f %m "$D/baseline.md")
  # 规则的口径是「早于扇出动作」；答案的 mtime 只能证明「早于第一份回答」，中间隔着整个
  # 网络往返。有 .fanout_started 就用它，那才是规则真正要求的那一刻。
  if [ -f "$D/.fanout_started" ]; then
    t=$(cat "$D/.fanout_started"); what="扇出起点"
  else
    t=$(for f in "$D"out/*.md; do [ -e "$f" ] && stat -f %m "$f"; done | sort -n | head -1)
    what="第一份答案（宽口径 —— 扇出块没落 .fanout_started）"
  fi
  if [ -z "$t" ]; then echo "⚠️  baseline.md   在，但没有可比的时间点"
  elif [ "$b" -lt "$t" ]; then echo "✅ baseline.md   早于${what}（早 $((t-b))s）"
  else echo "❌ baseline.md   晚于${what} $((b-t))s —— 已被污染"; fi
else echo "❌ baseline.md 缺失"; fi

if [ -f "$D/summary.md" ]; then echo "✅ summary.md    $(wc -c < "$D/summary.md" | tr -d ' ')B"
else echo "❌ summary.md 缺失 —— §3「Delivering it」要求 fork 自己用 Bash heredoc 落盘（Write 会被拦）"; fi

# baseline 的条目应当逐条变成矩阵里的一行（标 source: baseline）。数不上就是漏填了——
# 而漏填的恰恰是「五家全没提」的那些行，也就是集体盲区唯一的显影方式。
if [ -f "$D/baseline.md" ] && [ ! -f "$D/summary.md" ]; then
  echo "⚠️  未检查「baseline 条目→矩阵行」和「逐格引用回核」—— 两项都要 summary.md。"
  echo "    这是全套审计里唯一能显影「五家全没提」的一项，别让它默默不跑。"
fi
if [ -f "$D/baseline.md" ] && [ -f "$D/summary.md" ]; then
  # 只数**收尾那一份**清单：baseline.md 里常常不止一个编号列表（实测一份里有「3 条候选
  # 排序」+「5 条要点」两个），全数会得 8，然后诬告一份其实一条没漏的矩阵。取最后一段
  # 连续编号行 —— §2 要求的就是「以最多五条的清单收尾」。
  b=$(awk '/^[[:space:]]*[0-9]+[.、)]/ { c = (NR == p + 1) ? c + 1 : 1; p = NR } END { print c + 0 }' "$D/baseline.md" 2>/dev/null); b=${b:-0}
  # 中英两种写法都要认：实测汇总写的是 `(源:基线)`，纯中文，旧模式只认 baseline 这个词。
  m=$(grep -ciE 'source[:：] *baseline|源[:：] *(baseline|基线)' "$D/summary.md" 2>/dev/null); m=${m:-0}
  if [ "$b" -eq 0 ]; then echo "⚠️  baseline 没有编号条目 —— §2 要求它以「最多五条」的清单收尾"
  elif [ "$m" -ge "$b" ]; then echo "✅ baseline 条目 ${b} 条，矩阵里标注 ${m} 行"
  else echo "❌ baseline ${b} 条，矩阵只标了 ${m} 行 —— 少的那些正是「五家全没提」的行"; fi
fi

# 逐格引用回核：矩阵每个非「didn't mention」格要带 «原文片段»，这里拿回原文 grep。
# 唯一能显影「汇总把话安在谁头上」的一项 —— 用户只读汇总，而汇总层的误引率从没被测过
# （panelist 层测到过 4/6 编造）。
# 归属有两种写法，都要认：表格里靠**列头**点名（自然写法，格子里只有「同意 «…»」），
# 正文里靠**紧贴的模型名**点名（`模型«…»`）。第一版只认后者，于是把一张引用齐全的表
# 判成「零条引用」—— 在列头已经点名的表里再重复一遍模型名，本来就是冗余。
if [ -f "$D/summary.md" ]; then
  MODELS=$(for f in "$D"out/*.md; do [ -e "$f" ] && basename "$f" .md; done | tr '\n' ' ')
  P=$(mktemp); F=$(mktemp); TAB=$(printf '\t')
  awk -v models="$MODELS" '
    BEGIN { nm = split(models, M, " ") }
    # 简称要能落回全名：表头写 `deepseek` 而文件叫 deepseek-flash.md 是自然写法。认不出来
    # 的原样返回，好让下游报「没有这个模型的答案文件」—— 幽灵模型名不能被悄悄吸收掉。
    function resolve(name,   i, hit, c) {
      for (i = 1; i <= nm; i++) if (name == M[i]) return M[i]
      c = 0; for (i = 1; i <= nm; i++) if (length(name) >= 4 && index(M[i], name) == 1) { hit = M[i]; c++ }
      return (c == 1) ? hit : name
    }
    # 用 split 拆 «» 而不是 match/substr 算偏移：awk 有的按字节有的按字符，算偏移不可移植
    function emit(mod, s,   a, b, n, i) {
      n = split(s, a, "«")
      for (i = 2; i <= n; i++) { split(a[i], b, "»"); if (length(b[1]) >= 6) print mod "\t" b[1] }
    }
    /^[[:space:]]*\|/ {
      nc = split($0, C, "|"); hits = 0; split("", T)
      for (c = 1; c <= nc; c++) {
        cell = C[c]; gsub(/[`*[:space:]]/, "", cell); r = resolve(cell)
        for (i = 1; i <= nm; i++) if (r == M[i]) { T[c] = M[i]; hits++ }
      }
      if (hits >= 2) { split("", COL); for (c in T) COL[c] = T[c]; next }   # 表头：记下列→模型
      for (c = 1; c <= nc; c++) if (c in COL) emit(COL[c], C[c])
      next
    }
    # 正文：紧贴 « 前面那串标识符就是它声称的出处
    { n = split($0, a, "«")
      for (i = 2; i <= n; i++) {
        if (match(a[i-1], /[A-Za-z0-9_.-]+$/)) {
          split(a[i], b, "»")
          if (length(b[1]) >= 6) print resolve(substr(a[i-1], RSTART)) "\t" b[1]
        }
      } }
  ' "$D/summary.md" > "$P" 2>/dev/null
  tot=0; bad=0
  while IFS="$TAB" read -r m q; do
    [ -n "$m" ] && [ -n "$q" ] || continue
    # 两边同样压平：`*` 和反引号是汇总自己加的强调，原文里没有；空白差异也不算数。
    q=$(printf '%s' "$q" | tr -d '*`' | tr -s '[:space:]' ' ')
    [ -n "$q" ] || continue
    tot=$((tot+1))
    src="$D"out/"$m".md
    if [ ! -f "$src" ]; then
      bad=$((bad+1)); printf "  ❌ %-14s 没有这个模型的答案文件\n" "$m"; continue
    fi
    tr -d '*`' < "$src" | tr -s '[:space:]' ' ' > "$F"
    # 允许省略式引用 «A…B»，但要求**每一段**都能对上 —— 整串直接 grep 会把合法的省略
    # 判成编造（实测第一场就误伤一条，两半在原文里都在）。代价说清楚：这放过了「把相隔
    # 很远的两句拼成一句」，段内真实、拼接失真的那种误引，本项检不出来。
    # 必须 `%s\n`：不带换行结尾时 read 返回非零，内层循环一次都不跑，每一条都空过成"通过"
    # ——实测就是这样假绿了一整轮 51 条。切分交给 awk，不用 tr：tr 按字节切，`…` 是三字节。
    printf '%s\n' "$q" | awk '{ n = split($0, a, /…|\.\.\./); for (i = 1; i <= n; i++) print a[i] }' > "$P.frag"
    ok=1
    while IFS= read -r fr; do
      fr=$(printf '%s' "$fr" | sed 's/^ *//; s/ *$//')
      [ -n "$fr" ] && [ "$(printf '%s' "$fr" | wc -c)" -ge 6 ] || continue
      grep -Fq -- "$fr" "$F" || ok=0
    done < "$P.frag"
    [ "$ok" = 1 ] || { bad=$((bad+1)); printf "  ❌ %-14s «%s…» 原文里找不到\n" "$m" "$(printf '%s' "$q" | cut -c1-48)"; }
  done < "$P"
  rm -f "$P" "$F"
  if   [ "$tot" -eq 0 ]; then echo "⚠️  矩阵零条逐格引用 —— §3.1 要求非「didn't mention」的格都带 «原文»"
  elif [ "$bad" -eq 0 ]; then echo "✅ 逐格引用    ${tot} 条，全部能在原文里找到"
  else echo "❌ 逐格引用    ${tot} 条，${bad} 条回原文找不到 —— 汇总层误引"; fi
fi

echo
echo "出席（阈值：<200 ABSENT / <3000 UNUSABLE，两者都算缺席）"   # 与 SKILL.md §2 同步
miss=0; n=0
for f in "$D"out/*.md; do
  [ -e "$f" ] || continue
  n=$((n+1)); s=$(wc -c < "$f" | tr -d ' '); m=$(basename "$f" .md); e=$(cat "$D"out/"$m".err 2>/dev/null)
  if   [ "$s" -lt 200 ];  then t="ABSENT";   miss=$((miss+1))
  elif [ "$s" -lt 3000 ]; then t="UNUSABLE"; miss=$((miss+1))
  elif [ -n "$e" ];       then t="TRUNCATED"
  else                         t="ok"; fi
  # 第一次尝试失败会把错误存进 try1.err（成功的第二次会覆盖掉 .err）——不标出来就无从知道
  # 这家是一把过还是靠重试捡回来的，而"总要重试"本身就是该换路由的信号。分档只看 .err，
  # 重试痕迹只进展示：靠重试拿到的完整答案是 ok，不是 TRUNCATED。
  [ -f "$D"out/"$m".try1.err ] && e="[重试1次] $(cat "$D"out/"$m".try1.err 2>/dev/null) $e"
  printf "  %-10s %-16s %8sB  %s\n" "$t" "$m" "$s" "$(echo "$e" | tr '\n' ' ' | cut -c1-56)"
done
echo
echo "到场 $((n-miss))/${n}，缺席 ${miss}（≥2 应触发重跑，≥3 不该出汇总）"
echo "注：字节分档只是初筛。判不出「通篇只有工具调用旁白、没写出结论」——"
echo "    实测有一份 3.3KB 压线判 ok，读了才知道没有结论。最终以读过文件为准。"
