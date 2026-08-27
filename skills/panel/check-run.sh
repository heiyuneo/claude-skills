#!/bin/sh
# 验收一次 panel 跑：产物是否齐、baseline 时序是否可证、五家出席情况。
# 用法：sh ~/.claude/skills/panel/check-run.sh [归档目录]   （省略则取最近一次）
D="${1:-$(ls -dt ~/.claude/panel-runs/*/ 2>/dev/null | head -1)}"
case "$D" in */) ;; *) D="$D/";; esac
[ -d "$D" ] || { echo "找不到归档目录"; exit 1; }
echo "归档: $D"
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
else echo "❌ summary.md 缺失 —— fork 写不了盘，调用方没照末尾那句落盘"; fi

# baseline 的条目应当逐条变成矩阵里的一行（标 source: baseline）。数不上就是漏填了——
# 而漏填的恰恰是「五家全没提」的那些行，也就是集体盲区唯一的显影方式。
if [ -f "$D/baseline.md" ] && [ ! -f "$D/summary.md" ]; then
  echo "⚠️  未检查「baseline 条目→矩阵行」—— 需要 summary.md，而它要调用方落盘。"
  echo "    这是全套审计里唯一能显影「五家全没提」的一项，别让它默默不跑。"
fi
if [ -f "$D/baseline.md" ] && [ -f "$D/summary.md" ]; then
  # grep -c 无匹配时会打印 0 并返回 1；别再接 `|| echo 0`，那会拼出 "0\n0"
  b=$(grep -cE '^[[:space:]]*[0-9]+[.、)]' "$D/baseline.md" 2>/dev/null); b=${b:-0}
  m=$(grep -ciE 'source: *baseline|源[:：] *baseline' "$D/summary.md" 2>/dev/null); m=${m:-0}
  if [ "$b" -eq 0 ]; then echo "⚠️  baseline 没有编号条目 —— §2 要求它以「最多五条」的清单收尾"
  elif [ "$m" -ge "$b" ]; then echo "✅ baseline 条目 ${b} 条，矩阵里标注 ${m} 行"
  else echo "❌ baseline ${b} 条，矩阵只标了 ${m} 行 —— 少的那些正是「五家全没提」的行"; fi
fi

# 逐格引用回核：矩阵每个非「didn't mention」格要带 模型«原文片段»，这里拿回原文 grep。
# 唯一能显影「汇总把话安在谁头上」的一项 —— 用户只读汇总，而汇总层的误引率从没被测过
# （panelist 层测到过 4/6 编造）。空白差异不算数，两边都压平后再比。
if [ -f "$D/summary.md" ]; then
  P=$(mktemp); F=$(mktemp)
  grep -o '[A-Za-z][A-Za-z0-9_.-]*«[^»]\{6,\}»' "$D/summary.md" > "$P" 2>/dev/null
  tot=0; bad=0
  while IFS= read -r pair; do
    [ -n "$pair" ] || continue
    m=${pair%%«*}; q=${pair#*«}; q=${q%»}
    q=$(printf '%s' "$q" | tr -s '[:space:]' ' ')
    [ -n "$q" ] || continue
    tot=$((tot+1))
    src=$(ls "$D"out/"$m"*.md 2>/dev/null | head -1)
    if [ -z "$src" ]; then
      bad=$((bad+1)); printf "  ❌ %-14s 没有这个模型的答案文件\n" "$m"; continue
    fi
    tr -s '[:space:]' ' ' < "$src" > "$F"
    grep -Fq -- "$q" "$F" || { bad=$((bad+1)); printf "  ❌ %-14s «%s…» 原文里找不到\n" "$m" "$(printf '%s' "$q" | cut -c1-40)"; }
  done < "$P"
  rm -f "$P" "$F"
  if   [ "$tot" -eq 0 ]; then echo "⚠️  矩阵零条逐格引用 —— §3.1 要求非「didn't mention」的格都带 模型«原文»"
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
