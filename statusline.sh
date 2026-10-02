#!/usr/bin/env bash
# Claude Code status line — single line, width-aware, labelled
# model · folder · git · badges · context left · plan limits · date+time
# Docs: https://code.claude.com/docs/en/statusline
#
# NOTE ON COST: the dollar figure Claude Code reports is computed locally from
# token counts at API list rates. On a Pro/Max subscription usage is included in
# the plan, so that number is not a bill. The real budget is the rate limits
# below, so this status line shows those instead.

input=$(cat)

# One jq call for everything (cheap: this runs on every assistant message).
# Fields are joined with U+001F (unit separator), NOT tab: tab is an IFS
# whitespace char, so bash collapses runs of them and any empty field would
# silently shift every later field along by one.
IFS=$'\037' read -r MODEL DIR CTX_LEFT CTX_SIZE RL7 EFFORT FAST RL5 THINK <<EOF
$(printf '%s' "$input" | jq -r '[
    (.model.display_name // "?"),
    (.workspace.current_dir // .cwd // ""),
    (.context_window.remaining_percentage // 100),
    (.context_window.context_window_size // 0),
    (.rate_limits.seven_day.used_percentage // -1),
    (.effort.level // ""),
    (.fast_mode // false),
    (.rate_limits.five_hour.used_percentage // -1),
    (.thinking.enabled // false)
  ] | map(tostring) | join("")' 2>/dev/null)
EOF

MODEL=${MODEL:-?}
case "$CTX_LEFT" in ''|*[!0-9.]*) CTX_LEFT=100 ;; esac
case "$CTX_SIZE" in ''|*[!0-9.]*) CTX_SIZE=0 ;; esac
case "$EFFORT"   in false|null|-1) EFFORT="" ;; esac

# ── colours (legible on a light terminal theme) ──
R=$'\033[0m'; DIM=$'\033[2m'; B=$'\033[1m'
CYAN=$'\033[36m'; BLUE=$'\033[34m'; GREEN=$'\033[32m'
YELLOW=$'\033[33m'; RED=$'\033[31m'; MAGENTA=$'\033[35m'
S="${DIM} · ${R}"; SP=" · "          # coloured separator / plain mirror

WIDTH=${COLUMNS:-120}
case "$WIDTH" in ''|*[!0-9]*) WIDTH=120 ;; esac
[ "$WIDTH" -lt 20 ] && WIDTH=120
TIGHT=0; [ "$WIDTH" -lt 60 ] && TIGHT=1

# Rendered width: bash counts codepoints, but these glyphs occupy 2 columns.
vislen() {
  local s="$1" n=${#1} extra=0 t ch
  for ch in "📁" "🕐" "🧠" "⚡" "⏺"; do
    t=${s//"$ch"/}
    extra=$(( extra + n - ${#t} ))
  done
  printf '%s' $(( n + extra ))
}

# ── model ──
CTX_INT=${CTX_SIZE%%.*}
M_STR="${B}${CYAN}⏺ ${MODEL}${R}"; M_P="⏺ ${MODEL}"
if [ "${CTX_INT:-0}" -ge 1000000 ] 2>/dev/null; then
  M_STR="${M_STR}${DIM} 1M${R}"; M_P="${M_P} 1M"
fi

# ── folder ──
if [ "$DIR" = "$HOME" ]; then FOLDER="~"
elif [ -n "$DIR" ]; then FOLDER="${DIR##*/}"
else FOLDER="?"; fi
[ ${#FOLDER} -gt 24 ] && FOLDER="${FOLDER:0:23}…"
F_STR="${S}${BLUE}📁 ${FOLDER}${R}"; F_P="${SP}📁 ${FOLDER}"

# ── git ──
GIT_STR=""; GIT_P=""
if [ -n "$DIR" ] && git -C "$DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  BRANCH=$(git -C "$DIR" branch --show-current 2>/dev/null)
  [ -z "$BRANCH" ] && BRANCH=$(git -C "$DIR" rev-parse --short HEAD 2>/dev/null)
  if [ -n "$BRANCH" ]; then
    [ ${#BRANCH} -gt 18 ] && BRANCH="${BRANCH:0:17}…"
    D_STR=""; D_P=""
    if [ -n "$(git -C "$DIR" status --porcelain --untracked-files=no 2>/dev/null | head -1)" ]; then
      D_STR="${YELLOW}*${R}"; D_P="*"
    fi
    GIT_STR="${S}${MAGENTA}⑂ ${BRANCH}${R}${D_STR}"; GIT_P="${SP}⑂ ${BRANCH}${D_P}"
  fi
fi

# ── badges ──
EFF_STR=""; EFF_P=""
[ -n "$EFFORT" ] && { EFF_STR="${S}${DIM}effort ${EFFORT}${R}"; EFF_P="${SP}effort ${EFFORT}"; }
THK_STR=""; THK_P=""
[ "$THINK" = "true" ] && { THK_STR="${DIM} 🧠${R}"; THK_P=" 🧠"; }
FST_STR=""; FST_P=""
[ "$FAST" = "true" ] && { FST_STR="${S}${YELLOW}⚡fast${R}"; FST_P="${SP}⚡fast"; }

# ── context remaining ──
LEFT=${CTX_LEFT%%.*}; LEFT=${LEFT:-100}
[ "$LEFT" -lt 0 ] 2>/dev/null && LEFT=0
[ "$LEFT" -gt 100 ] 2>/dev/null && LEFT=100
if   [ "$LEFT" -ge 50 ]; then CC=$GREEN
elif [ "$LEFT" -ge 20 ]; then CC=$YELLOW
else                          CC=$RED; fi
if [ $TIGHT -eq 1 ]; then
  CTX_STR="${S}${DIM}ctx ${R}${CC}${LEFT}%${R}"; CTX_P="${SP}ctx ${LEFT}%"
else
  SLOTS=6; FILLED=$(( (LEFT * SLOTS + 50) / 100 ))
  [ "$FILLED" -gt "$SLOTS" ] && FILLED=$SLOTS
  [ "$FILLED" -lt 0 ] && FILLED=0
  BAR=""; i=0
  while [ $i -lt $FILLED ]; do BAR="${BAR}█"; i=$((i+1)); done
  while [ $i -lt $SLOTS ];  do BAR="${BAR}░"; i=$((i+1)); done
  CTX_STR="${S}${DIM}ctx ${R}${CC}${BAR} ${LEFT}% left${R}"
  CTX_P="${SP}ctx ${BAR} ${LEFT}% left"
fi

# ── plan limits: how much of each rolling window is USED ──
# colour: quiet while there's room, amber at 75%, red at 90%
limit_colour() {
  if   [ "$1" -ge 90 ]; then printf '%s' "$RED"
  elif [ "$1" -ge 75 ]; then printf '%s' "$YELLOW"
  elif [ "$1" -ge 50 ]; then printf '%s' "$R"
  else                       printf '%s' "$DIM"; fi
}
RL5_STR=""; RL5_P=""
V=${RL5%%.*}
if [ -n "$V" ] && [ "$V" -ge 0 ] 2>/dev/null; then
  C=$(limit_colour "$V")
  RL5_STR="${S}${DIM}5h used ${R}${C}${V}%${R}"; RL5_P="${SP}5h used ${V}%"
fi
RL7_STR=""; RL7_P=""
V=${RL7%%.*}
if [ -n "$V" ] && [ "$V" -ge 0 ] 2>/dev/null; then
  C=$(limit_colour "$V")
  RL7_STR="${S}${DIM}week used ${R}${C}${V}%${R}"; RL7_P="${SP}week used ${V}%"
fi

# ── time ──
if [ $TIGHT -eq 1 ]; then NOW=$(date '+%H:%M'); else NOW=$(date '+%a %-d %b %H:%M'); fi
T_STR="${DIM} · 🕐 ${NOW}${R}"; T_P="${SP}🕐 ${NOW}"

# ── assemble, dropping optional segments until it fits ──
assemble() {
  LINE="${M_STR}${F_STR}${GIT_STR}${EFF_STR}${THK_STR}${FST_STR}${CTX_STR}${RL5_STR}${RL7_STR}${T_STR}"
  PLAIN="${M_P}${F_P}${GIT_P}${EFF_P}${THK_P}${FST_P}${CTX_P}${RL5_P}${RL7_P}${T_P}"
}
MAX=$(( WIDTH - 1 ))
assemble
for seg in THK EFF FST GIT RL7 RL5; do
  [ "$(vislen "$PLAIN")" -le "$MAX" ] && break
  eval "${seg}_STR=''; ${seg}_P=''"
  assemble
done

# Nothing optional left to drop: shorten time, then the 1M marker, then the folder.
if [ "$(vislen "$PLAIN")" -gt "$MAX" ]; then
  NOW=$(date '+%H:%M'); T_STR="${DIM} · 🕐 ${NOW}${R}"; T_P="${SP}🕐 ${NOW}"
  assemble
fi
if [ "$(vislen "$PLAIN")" -gt "$MAX" ]; then
  M_STR="${B}${CYAN}⏺ ${MODEL}${R}"; M_P="⏺ ${MODEL}"
  assemble
fi
if [ "$(vislen "$PLAIN")" -gt "$MAX" ]; then
  over=$(( $(vislen "$PLAIN") - MAX ))
  keep=$(( ${#FOLDER} - over - 1 ))
  [ "$keep" -lt 5 ] && keep=5
  if [ "$keep" -lt ${#FOLDER} ]; then
    FOLDER="${FOLDER:0:$keep}…"
    F_STR="${S}${BLUE}📁 ${FOLDER}${R}"; F_P="${SP}📁 ${FOLDER}"
    assemble
  fi
fi

printf '%b\n' "$LINE"
