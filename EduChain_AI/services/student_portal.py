"""학생 포털 — 개요·수업 개요·주차별 수강(영상 + 우측 패널)."""

from __future__ import annotations

import html
import json
import random
import re
import time
from typing import Any

import streamlit as st
from firebase_admin import auth as fb_auth
import streamlit.components.v1 as components

from services import gemini_client
from services import ui_messages
from services.firebase_app import init_firebase
from services.firestore_repo import (
    append_student_lesson_question,
    get_content_category,
    get_lesson_progress_doc_id,
    get_lesson_week,
    get_student_lesson_progress_fields,
    get_student_lesson_progress_percent,
    list_lesson_weeks,
    merge_student_lesson_quiz_result,
    reset_student_lesson_quiz_progress,
)
from services.quiz_items import (
    draw_quiz_pool_indices,
    parse_quiz_pool_indices_saved,
    quiz_pass_min_for_session,
    quiz_pool_for_week,
    quiz_preview_session_pair,
    quiz_session_params,
    quiz_want_count,
)
from services.lesson_access import week_in_student_list, week_is_visible_to_student
from services.session_keys import (
    AUTH_DISPLAY_NAME,
    AUTH_EMAIL,
    AUTH_UID,
    STUDENT_COURSE_SUB_TAB,
    STUDENT_LEARN_CATEGORY_FP,
    STUDENT_LEARN_WEEK_ID,
    STUDENT_QUIZ_WEEK_ID,
    STUDENT_VIEW_TAB,
)


def _player_column_resize_css(open_now: bool) -> str:
    """우측 패널 접힘 시 fragment만 rerun되므로, 열 너비는 CSS로 덮어씀(영상 iframe 유지)."""
    if open_now:
        c1, c2, mw2 = "1.72", "0.78", "22rem"
    else:
        c1, c2, mw2 = "36", "1", "5rem"
    return f"""
<style>
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(1) {{
    flex: {c1} 1 0% !important;
    max-width: none !important;
    min-width: 0 !important;
  }}
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) {{
    flex: {c2} 1 0% !important;
    max-width: {mw2} !important;
    min-width: 0 !important;
  }}
</style>
"""


def _streamlit_fragment_decorator() -> Any:
    """st.fragment(1.38+) 또는 experimental_fragment(1.33+). 없으면 None → 전체 rerun."""
    deco = getattr(st, "fragment", None)
    if callable(deco):
        return deco
    deco = getattr(st, "experimental_fragment", None)
    if callable(deco):
        return deco
    return None


def pick_current_week_for_student(weeks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    공개 설정상 열람 가능한 주차 중 week_index 가 가장 큰 주차를 '현재 주차'로 본다.
    (라이브/캘린더 연동 없이 커리큘럼 진행 기준)
    """
    visible: list[dict[str, Any]] = []
    for w in weeks:
        ok, _ = week_is_visible_to_student(w)
        if ok:
            visible.append(w)
    if not visible:
        return None
    return max(visible, key=lambda x: int(x.get("week_index") or 0))


def _youtube_embed_src(url: str) -> str | None:
    u = (url or "").strip()
    if not u:
        return None
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})", u)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    m2 = re.search(r"youtube\.com/embed/([\w-]+)", u)
    if m2:
        return f"https://www.youtube.com/embed/{m2.group(1)}"
    return None


def _vimeo_embed_src(url: str) -> str | None:
    u = (url or "").strip()
    if not u or "vimeo.com" not in u.lower():
        return None
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)", u)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    return None


def _youtube_video_id(url: str) -> str | None:
    u = (url or "").strip()
    if not u:
        return None
    m = re.search(
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{11})", u
    )
    return m.group(1) if m else None


def _vimeo_numeric_id(url: str) -> str | None:
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)", (url or "").lower())
    return m.group(1) if m else None


def _firebase_web_config_from_secrets() -> dict[str, str] | None:
    try:
        if not hasattr(st, "secrets"):
            return None
        s = st.secrets
        api = str(s.get("FIREBASE_WEB_API_KEY") or "").strip()
        pid = str(s.get("FIREBASE_PROJECT_ID") or "").strip()
        dom = str(s.get("FIREBASE_AUTH_DOMAIN") or "").strip()
        if not api or not pid or not dom:
            return None
        return {"apiKey": api, "authDomain": dom, "projectId": pid}
    except Exception:
        return None


def _build_lesson_video_progress_html(payload: dict[str, Any]) -> str:
    """Firebase Auth(커스텀 토큰) + Firestore로 시청 진행률 자동 저장 (YouTube/Vimeo/HTML5)."""
    j = json.dumps(payload, ensure_ascii=False)
    tpl = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  html, body { margin:0; padding:0; width:100%; height:auto; min-height:0; background:#000; }
  #mount { width:100%; line-height:0; }
  /* YT.Player가 iframe에 기본 640x390 등을 넣어 위·아래 검은 빈칸이 생기므로 꽉 채움 */
  #yt-player {
    width:100%;
    aspect-ratio:16/9;
    position:relative;
    background:#000;
    border-radius:8px;
    overflow:hidden;
  }
  #yt-player iframe {
    position:absolute !important;
    top:0 !important;
    left:0 !important;
    width:100% !important;
    height:100% !important;
    border:0 !important;
  }
  .lesson-video-wrap { position:relative; width:100%; aspect-ratio:16/9; background:#000; border-radius:8px; overflow:hidden; }
</style>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-auth-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-firestore-compat.js"></script>
</head>
<body>
<script type="application/json" id="stu-video-payload">__PAYLOAD__</script>
<div id="mount"></div>
<script>
(function() {
  var P = JSON.parse(document.getElementById("stu-video-payload").textContent);
  firebase.initializeApp(P.firebase);
  function makeProgress() {
    var maxPct = P.progress.initialPercent || 0;
    return function(pct) {
      pct = Math.round(Math.max(0, Math.min(100, pct)));
      if (pct <= maxPct) return;
      maxPct = pct;
      firebase.firestore().collection("Users").doc(P.progress.uid)
        .collection("LessonProgress").doc(P.progress.docId)
        .set({
          org_id: P.progress.orgId,
          category_id: P.progress.categoryId,
          week_doc_id: P.progress.weekDocId,
          progress_percent: maxPct,
          updated_at: firebase.firestore.FieldValue.serverTimestamp()
        }, { merge: true }).catch(function(e) { console.error(e); });
    };
  }
  var saveProgress = makeProgress();
  var lastVideoPosSave = 0;
  function saveVideoPosition(sec, dur) {
    if (typeof sec !== "number" || isNaN(sec) || sec < 0) return;
    var now = Date.now();
    if (now - lastVideoPosSave < 2500) return;
    lastVideoPosSave = now;
    var data = {
      org_id: P.progress.orgId,
      category_id: P.progress.categoryId,
      week_doc_id: P.progress.weekDocId,
      last_video_position_sec: sec,
      updated_at: firebase.firestore.FieldValue.serverTimestamp()
    };
    if (typeof dur === "number" && !isNaN(dur) && dur > 0) {
      data.video_duration_sec = dur;
    }
    firebase.firestore().collection("Users").doc(P.progress.uid)
      .collection("LessonProgress").doc(P.progress.docId)
      .set(data, { merge: true }).catch(function(e) { console.error(e); });
  }
  firebase.auth().signInWithCustomToken(P.auth.token).then(function() {
    var mount = document.getElementById("mount");
    if (P.kind === "youtube") {
      mount.innerHTML = '<div id="yt-player"></div>';
      window.onYouTubeIframeAPIReady = function() {
        var player = new YT.Player("yt-player", {
          videoId: P.youtube.videoId,
          playerVars: { rel: 0, modestbranding: 1 },
          events: {
            onReady: function(e) {
              try {
                var ifr = e.target.getIframe();
                if (ifr) {
                  ifr.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;border:0;";
                }
                var d = e.target.getDuration();
                var pct = P.progress.initialPercent || 0;
                if (d > 0 && pct > 0 && pct < 100) {
                  e.target.seekTo(d * pct / 100, true);
                }
              } catch (err) {}
            },
            onStateChange: function(e) {
              if (e.data === YT.PlayerState.ENDED) {
                saveProgress(100);
                try {
                  var d = e.target.getDuration();
                  var c = e.target.getCurrentTime();
                  if (d > 0) saveVideoPosition(c, d);
                } catch (err3) {}
              }
              if (e.data === YT.PlayerState.PAUSED) {
                try {
                  var d = e.target.getDuration();
                  var c = e.target.getCurrentTime();
                  if (d > 0) {
                    saveProgress(Math.round(c / d * 100));
                    saveVideoPosition(c, d);
                  }
                } catch (err2) {}
              }
            }
          }
        });
        setInterval(function() {
          try {
            if (player.getPlayerState && player.getPlayerState() === YT.PlayerState.PLAYING) {
              var d = player.getDuration();
              var c = player.getCurrentTime();
              if (d > 0) {
                saveProgress(Math.round(c / d * 100));
                saveVideoPosition(c, d);
              }
            }
          } catch (err) {}
        }, 5000);
      };
      var tag = document.createElement("script");
      tag.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(tag);
      return;
    }
    if (P.kind === "vimeo") {
      mount.innerHTML = '<div class="lesson-video-wrap"><iframe id="vimeo-player" src="https://player.vimeo.com/video/'
        + P.vimeo.videoId + '" allowfullscreen allow="autoplay; fullscreen" style="position:absolute;inset:0;width:100%;height:100%;border:0;"></iframe></div>';
      var s = document.createElement("script");
      s.src = "https://player.vimeo.com/api/player.js";
      s.onload = function() {
        var iframe = document.getElementById("vimeo-player");
        var vp = new Vimeo.Player(iframe);
        var durC = 0;
        vp.getDuration().then(function(d) {
          durC = d;
          var pct = P.progress.initialPercent || 0;
          if (d > 0 && pct > 0 && pct < 100) {
            vp.setCurrentTime(d * pct / 100).catch(function() {});
          }
        });
        vp.on("timeupdate", function(data) {
          if (durC > 0) {
            saveProgress(Math.round(data.seconds / durC * 100));
            saveVideoPosition(data.seconds, durC);
          }
        });
        vp.on("ended", function() {
          saveProgress(100);
          if (durC > 0) saveVideoPosition(durC, durC);
        });
        vp.on("pause", function() {
          vp.getDuration().then(function(d) {
            vp.getCurrentTime().then(function(c) {
              if (d > 0) {
                saveProgress(Math.round(c / d * 100));
                saveVideoPosition(c, d);
              }
            });
          });
        });
      };
      document.head.appendChild(s);
      return;
    }
    if (P.kind === "html5") {
      var v = document.createElement("video");
      v.id = "html5v";
      v.src = P.html5.src;
      v.controls = true;
      v.setAttribute("playsinline", "");
      v.style.cssText = "width:100%;aspect-ratio:16/9;background:#000;border-radius:8px;display:block;";
      mount.appendChild(v);
      v.addEventListener("loadedmetadata", function() {
        var d = v.duration;
        var pct = P.progress.initialPercent || 0;
        if (d > 0 && pct > 0 && pct < 100) {
          v.currentTime = d * pct / 100;
        }
      });
      v.addEventListener("timeupdate", function() {
        if (v.duration) {
          saveProgress(Math.round(v.currentTime / v.duration * 100));
          saveVideoPosition(v.currentTime, v.duration);
        }
      });
      v.addEventListener("ended", function() {
        saveProgress(100);
        if (v.duration) saveVideoPosition(v.currentTime, v.duration);
      });
      v.addEventListener("pause", function() {
        if (v.duration) {
          saveProgress(Math.round(v.currentTime / v.duration * 100));
          saveVideoPosition(v.currentTime, v.duration);
        }
      });
    }
  }).catch(function(e) { console.error(e); });
})();
</script>
</body></html>
"""
    return tpl.replace("__PAYLOAD__", j)


def _inject_learn_player_css() -> None:
    """수강 플레이어: 앱 사이드바 숨김, 영상 16:9, 모드 버튼(사이드바 톤) 스타일."""
    st.markdown(
        """
<style>
  section[data-testid="stSidebar"] { display: none !important; }
  div[data-testid="collapsedControl"] { display: none !important; }
  section[data-testid="stMain"] > div { padding-left: 1.25rem !important; padding-right: 1.25rem !important; }
  section[data-testid="stMain"] video {
    aspect-ratio: 16 / 9 !important;
    width: 100% !important;
    object-fit: contain !important;
    background: #000 !important;
    border-radius: 8px !important;
    max-height: min(72vh, 720px) !important;
  }
  section[data-testid="stMain"] div[data-testid="stVideo"] {
    width: 100% !important;
    aspect-ratio: 16 / 9 !important;
    max-height: min(72vh, 720px) !important;
  }
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(3):last-child) > div[data-testid="column"] .stButton > button[data-testid="baseButton-secondary"] {
    width: 100% !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: inherit !important;
    font-weight: 400 !important;
    justify-content: center !important;
    text-align: center !important;
    padding: 0.375rem 0.5rem !important;
    min-height: 2.5rem !important;
    border-radius: 0.375rem !important;
  }
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(3):last-child) > div[data-testid="column"] .stButton > button[data-testid="baseButton-secondary"]:hover {
    background-color: rgba(151, 166, 195, 0.15) !important;
  }
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(3):last-child) > div[data-testid="column"] .stButton > button[data-testid="baseButton-primary"] {
    width: 100% !important;
    background: rgba(151, 166, 195, 0.2) !important;
    border: none !important;
    box-shadow: none !important;
    color: inherit !important;
    font-weight: 600 !important;
    justify-content: center !important;
    text-align: center !important;
    padding: 0.375rem 0.5rem !important;
    min-height: 2.5rem !important;
    border-radius: 0.375rem !important;
  }
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(3):last-child) > div[data-testid="column"] .stButton > button[data-testid="baseButton-primary"]:hover {
    background-color: rgba(151, 166, 195, 0.28) !important;
  }
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(3):last-child) > div[data-testid="column"] .stButton > button[data-testid="baseButton-secondary"],
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(3):last-child) > div[data-testid="column"] .stButton > button[data-testid="baseButton-primary"] {
    font-size: 0.78rem !important;
    min-height: 2.1rem !important;
    padding: 0.25rem 0.35rem !important;
  }
  /* 영상|우측패널 2열 블록(보통 본문 두 번째 가로 행) — 오른쪽 열 글자·여백 축소 */
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) {
    font-size: 0.86rem !important;
    line-height: 1.38 !important;
    max-width: 22rem !important;
  }
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) h1,
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) h2,
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) h3,
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) h4,
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) h5,
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) h6 {
    font-size: 0.88rem !important;
    margin-top: 0.15rem !important;
    margin-bottom: 0.25rem !important;
  }
  section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:nth-of-type(2) > div[data-testid="column"]:nth-child(2) [data-testid="stCaption"] {
    font-size: 0.78rem !important;
  }
</style>
""",
        unsafe_allow_html=True,
    )


def _inject_quiz_exam_css() -> None:
    """퀴즈 시험 전용: 사이드바 숨김 + 공무원·국가고시형 톤(남색 헤더·답안지 느낌)."""
    st.markdown(
        """
<style>
  section[data-testid="stSidebar"] { display: none !important; }
  div[data-testid="collapsedControl"] { display: none !important; }
  section[data-testid="stMain"] > div { padding-left: 1.25rem !important; padding-right: 1.25rem !important; }
  div.exam-paper {
    background: #fafbfd;
    border: 1px solid #c5d4e8;
    border-radius: 10px;
    padding: 1.1rem 1.25rem 1.25rem 1.25rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 12px rgba(13, 45, 90, 0.08);
  }
  div.exam-qhead {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    margin-bottom: 0.65rem;
  }
  span.exam-qno {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2rem;
    height: 2rem;
    border-radius: 50%;
    background: linear-gradient(180deg, #154a8c 0%, #0d2d5a 100%);
    color: #fff;
    font-weight: 700;
    font-size: 0.95rem;
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
  }
  div.exam-choices-wrap label {
    font-size: 0.95rem !important;
    line-height: 1.45 !important;
  }
</style>
""",
        unsafe_allow_html=True,
    )


def _escape_nl_br(text: str) -> str:
    return html.escape(text or "").replace("\n", "<br/>")


def _render_scrollable_chat_html(
    messages: list[dict[str, str]],
    *,
    height_px: int = 400,
) -> None:
    """고정 높이 + 내부 스크롤(채팅이 길어져도 레이아웃 유지)."""
    parts: list[str] = []
    for m in messages[-50:]:
        role = m.get("role") or "user"
        body = _escape_nl_br(m.get("content") or "")
        is_user = role == "user"
        bg = "rgba(255,255,255,0.98)" if is_user else "rgba(151,166,195,0.14)"
        icon = "👤" if is_user else "🤖"
        parts.append(
            f'<div style="margin:0 0 0.55rem 0;padding:0.5rem 0.65rem;border-radius:8px;'
            f"background:{bg};border:1px solid rgba(151,166,195,0.35);\">"
            f'<div style="font-size:0.72rem;opacity:0.75;margin-bottom:0.2rem;">{icon}</div>'
            f'<div style="font-size:0.92rem;line-height:1.5;">{body}</div>'
            "</div>"
        )
    inner = (
        "".join(parts)
        if parts
        else '<div style="opacity:0.65;font-size:0.9rem;">메시지가 없습니다.</div>'
    )
    scroll = (
        f'<div style="max-height:{height_px}px;overflow-y:auto;overflow-x:hidden;'
        "padding:0.4rem 0.45rem 0.5rem 0.35rem;border:1px solid rgba(151,166,195,0.35);"
        'border-radius:8px;background:#fafafa;">'
        f"{inner}</div>"
    )
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><style>body{{margin:0;font-family:sans-serif;}}</style></head><body>{scroll}</body></html>"""
    components.html(doc, height=min(height_px + 28, 520), scrolling=True)


def _render_overview_scroll_html(
    *,
    title: str,
    goals: str,
    preview: str,
    keywords: str,
    height_px: int = 400,
) -> None:
    parts: list[str] = []
    parts.append(f"<h3 style='margin:0 0 0.45rem 0;font-size:1.05rem;'>{html.escape(title)}</h3>")
    if goals.strip():
        parts.append("<h4 style='margin:0.55rem 0 0.25rem 0;font-size:0.95rem;'>학습 목표</h4>")
        parts.append(f"<div style='line-height:1.5;font-size:0.92rem;'>{_escape_nl_br(goals)}</div>")
    if preview.strip():
        parts.append("<h4 style='margin:0.55rem 0 0.25rem 0;font-size:0.95rem;'>이번 주차 핵심</h4>")
        parts.append(f"<div style='line-height:1.5;font-size:0.92rem;'>{_escape_nl_br(preview)}</div>")
    elif not goals.strip():
        parts.append("<p style='opacity:0.75;font-size:0.9rem;'>요약이 아직 없습니다.</p>")
    if keywords.strip():
        parts.append("<h4 style='margin:0.55rem 0 0.25rem 0;font-size:0.95rem;'>키워드</h4>")
        parts.append(f"<div style='font-size:0.88rem;opacity:0.9;'>{html.escape(keywords)}</div>")
    inner = "".join(parts) if parts else "<p>내용이 없습니다.</p>"
    scroll = (
        f'<div style="max-height:{height_px}px;overflow-y:auto;overflow-x:hidden;'
        "padding:0.45rem 0.5rem;border:1px solid rgba(151,166,195,0.35);"
        f'border-radius:8px;background:#fafafa;">{inner}</div>'
    )
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"/><style>body{{margin:0;font-family:sans-serif;}}</style></head><body>{scroll}</body></html>"""
    components.html(doc, height=min(height_px + 28, 520), scrolling=True)


def _render_simple_video_embed(video_url: str) -> None:
    """자동 진행률 없이 기존 방식(iframe / st.video)만 표시."""
    raw = (video_url or "").strip()
    if not raw:
        ui_messages.info_video_url_empty_student()
        return
    yt = _youtube_embed_src(raw)
    vm = _vimeo_embed_src(raw)
    src = yt or vm
    if src:
        safe = html.escape(src, quote=True)
        doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  html, body {{ margin:0; padding:0; width:100%; min-height:100%; background:#000; }}
  .lesson-video-wrap {{
    width:100%;
    max-width:100%;
    aspect-ratio:16/9;
    position:relative;
    background:#000;
    border-radius:8px;
    overflow:hidden;
  }}
  .lesson-video-wrap iframe {{
    position:absolute;
    inset:0;
    width:100%;
    height:100%;
    border:0;
  }}
</style></head>
<body>
  <div class="lesson-video-wrap">
    <iframe title="lesson-video" src="{safe}"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen></iframe>
  </div>
</body></html>"""
        components.html(doc, height=560, scrolling=False)
        return
    try:
        st.video(raw)
    except Exception:
        st.warning("영상을 바로 재생할 수 없습니다. 아래 링크로 열어 주세요.")
        st.markdown(f"[영상 열기]({raw})")


def _render_video_area(
    video_url: str,
    *,
    progress_uid: str | None = None,
    org_id: str | None = None,
    category_id: str | None = None,
    week_doc_id: str | None = None,
) -> None:
    raw = (video_url or "").strip()
    if not raw:
        ui_messages.info_video_url_empty_student()
        return

    want_auto = bool(
        progress_uid and org_id and category_id and week_doc_id
    )
    fb_cfg = _firebase_web_config_from_secrets() if want_auto else None
    custom_token: str | None = None
    doc_id: str | None = None
    initial_pct = 0
    if want_auto and fb_cfg:
        try:
            init_firebase()
            tok = fb_auth.create_custom_token(progress_uid)
            custom_token = tok.decode("utf-8") if isinstance(tok, bytes) else str(tok)
            doc_id = get_lesson_progress_doc_id(org_id, category_id, week_doc_id)
            initial_pct = get_student_lesson_progress_percent(
                progress_uid, org_id, category_id, week_doc_id
            )
        except Exception:
            custom_token = None
            doc_id = None

    auto_ok = bool(want_auto and fb_cfg and custom_token and doc_id)
    yt_id = _youtube_video_id(raw)
    vm_id = _vimeo_numeric_id(raw)

    if auto_ok:
        base_progress = {
            "uid": progress_uid,
            "docId": doc_id,
            "orgId": org_id,
            "categoryId": category_id,
            "weekDocId": week_doc_id,
            "initialPercent": initial_pct,
        }
        if yt_id:
            payload = {
                "firebase": fb_cfg,
                "auth": {"token": custom_token},
                "progress": base_progress,
                "kind": "youtube",
                "youtube": {"videoId": yt_id},
            }
            components.html(
                _build_lesson_video_progress_html(payload),
                height=560,
                scrolling=False,
            )
            st.caption(
                "시청 진행률이 재생 중 주기적으로 자동 저장되며, 재생 완료 시 100%로 반영됩니다."
            )
            return
        if vm_id:
            payload = {
                "firebase": fb_cfg,
                "auth": {"token": custom_token},
                "progress": base_progress,
                "kind": "vimeo",
                "vimeo": {"videoId": vm_id},
            }
            components.html(
                _build_lesson_video_progress_html(payload),
                height=560,
                scrolling=False,
            )
            st.caption(
                "시청 진행률이 재생 중 주기적으로 자동 저장되며, 재생 완료 시 100%로 반영됩니다."
            )
            return
        payload = {
            "firebase": fb_cfg,
            "auth": {"token": custom_token},
            "progress": base_progress,
            "kind": "html5",
            "html5": {"src": raw},
        }
        components.html(
            _build_lesson_video_progress_html(payload),
            height=560,
            scrolling=False,
        )
        st.caption(
            "시청 진행률이 재생 중 주기적으로 자동 저장되며, 재생 완료 시 100%로 반영됩니다."
        )
        return

    if want_auto and not auto_ok:
        st.caption(
            "자동 진행률 저장을 켤 수 없어 일반 재생만 표시합니다. "
            "(`.streamlit/secrets.toml`에 Firebase 웹 설정·Admin 자격이 필요합니다.)"
        )
    _render_simple_video_embed(raw)


def _display_week_title_for_student(title: str, week_index: int) -> str:
    """Firestore ``week_index`` 와 'N주차' 형태 제목을 맞춰 표기 (목록 순번과 혼동 금지)."""
    t = (title or "").strip()
    if not t:
        return f"{week_index}주차"
    if re.fullmatch(r"\d+주차", t):
        return f"{week_index}주차"
    return t


def _week_status_label(
    *,
    week: dict[str, Any],
    current_id: str | None,
    progress_pct: int | None = None,
) -> tuple[str, str]:
    """
    Returns (짧은 배지 텍스트, 부가 설명).
    비활성 | 비공개 | 수강완료(진행률 100%) | 수강 중 | 열람 가능
    """
    mode = str(week.get("access_mode") or "open").strip()
    if mode == "inactive":
        return "비활성", "수강은 준비 중입니다. 교사가 수업을 열면 이용할 수 있습니다."

    ok, reason = week_is_visible_to_student(week)
    wid = str(week.get("_doc_id") or "")
    if not ok:
        return "비공개", reason or "열람할 수 없습니다."
    if progress_pct is not None and progress_pct >= 100:
        return "수강완료", "이 회차 영상 시청을 완료했습니다."
    if current_id and wid == current_id:
        return "수강 중", "이번 진행 기준의 현재 주차입니다."
    return "열람 가능", "이 회차 자료를 열람할 수 있습니다."


def render_student_overview(
    *,
    org_name: str,
    display_name: str,
    email: str,
    courses: list[dict[str, Any]],
) -> None:
    st.markdown("##### 나의 정보")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**이름:** {display_name or '—'}")
        st.markdown(f"**이메일:** {email or '—'}")
    with c2:
        st.markdown(f"**소속:** {org_name or '—'}")
        st.markdown("**역할:** Student")

    st.divider()
    st.markdown("##### 전체 교과목 (배정된 수업)")
    if not courses:
        st.info(
            "아직 배정된 수업이 없습니다. 담당 교사에게 **수업 배정**을 요청하세요."
        )
        return
    for c in courses:
        cid = str(c.get("_doc_id") or "")
        nm = str(c.get("name") or "(이름 없음)")
        desc = str(c.get("description") or "").strip()
        with st.container():
            st.markdown(f"**📚 {nm}**")
            if desc:
                st.caption(desc[:300] + ("…" if len(desc) > 300 else ""))
            st.caption(f"수업 ID: `{cid}`")
        st.divider()


def render_student_course_overview(
    *,
    org_id: str,
    uid: str,
    category: dict[str, Any],
) -> None:
    name = str(category.get("name") or "(이름 없음)")
    desc = str(category.get("description") or "").strip()
    teacher_ov = str(category.get("teacher_overview") or "").strip()
    cat_id = str(category.get("_doc_id") or "").strip()

    st.markdown(f"### {name}")

    op_fb_stu = str(category.get("operator_feedback_student") or "").strip()
    if op_fb_stu:
        st.info(f"**운영자 공지**\n\n{op_fb_stu}")

    if desc:
        st.markdown("##### 운영자 안내")
        st.markdown(desc)

    st.markdown("##### 교사 수업 개요")
    if teacher_ov:
        st.markdown(teacher_ov)
    else:
        st.caption("교사가 아직 수업 개요를 작성하지 않았습니다.")

    st.markdown("##### 주차·수강 현황")
    st.caption("왼쪽 **제목**을 누르면 해당 주차 **수업 수강(강의)** 화면으로 이동합니다.")
    weeks = list_lesson_weeks(org_id, cat_id) if cat_id else []
    weeks_shown = [w for w in weeks if week_in_student_list(w)]
    if not weeks_shown:
        st.caption(
            "표시할 주차가 없습니다. 교사가 **수업 관리**에서 주차를 등록하면 여기에 나타납니다."
        )
        return

    for i, w in enumerate(weeks_shown, start=1):
        wid = str(w.get("_doc_id") or "").strip()
        wi = int(w.get("week_index") or 0)
        # DB week_index와 버튼 라벨을 맞춤 (목록 순번 i와 혼동 시 1칸 어긋남)
        label_week = wi if wi > 0 else i
        raw_title = str(w.get("title") or "").strip()
        display_title = _display_week_title_for_student(raw_title, label_week)
        ok, _reason = week_is_visible_to_student(w)
        pct = (
            get_student_lesson_progress_percent(uid, org_id, cat_id, wid)
            if ok and wid
            else None
        )
        if not ok:
            status = "열람 불가"
        elif pct is not None and pct >= 100:
            status = "수강완료"
        elif pct is not None and pct > 0:
            status = "진행 중"
        else:
            status = "미시작"
        pct_cell = f"{pct}%" if ok and pct is not None else "—"

        col_title, col_meta = st.columns([1.15, 2.1])
        with col_title:
            if st.button(
                display_title,
                key=f"stu_ov_open_{cat_id}_{wid}",
                disabled=not ok,
                use_container_width=True,
            ):
                st.session_state.pop(STUDENT_QUIZ_WEEK_ID, None)
                st.session_state[STUDENT_VIEW_TAB] = "course"
                st.session_state[STUDENT_COURSE_SUB_TAB] = "learn"
                st.session_state[STUDENT_LEARN_WEEK_ID] = wid
                st.switch_page("pages/5_Student.py")
        with col_meta:
            st.markdown(f"**주차** {label_week} · **수강 상태** {status}")
            if not ok and _reason:
                st.caption(_reason)
            st.caption(f"진행률: **{pct_cell}**")
        st.divider()

    st.caption(
        "**수강완료**는 진행률 100%일 때, **진행 중**은 1~99%일 때입니다. "
        "**열람 불가**는 공개·기간 설정으로 아직 수강할 수 없을 때입니다."
    )


def _reset_learn_player_if_course_changed(category_id: str) -> None:
    fp = str(category_id).strip()
    prev = st.session_state.get(STUDENT_LEARN_CATEGORY_FP)
    if prev != fp:
        st.session_state[STUDENT_LEARN_CATEGORY_FP] = fp
        st.session_state.pop(STUDENT_LEARN_WEEK_ID, None)
        st.session_state.pop(STUDENT_QUIZ_WEEK_ID, None)


def _sync_quiz_attempt_if_needed(
    uid: str,
    org_id: str,
    category_id: str,
    week_doc_id: str,
) -> None:
    """레거시: 채점 결과는 있는데 ``quiz_attempt_count``만 0인 문서를 한 번 merge로 맞춘다."""
    if not uid or not org_id or not category_id or not week_doc_id:
        return
    pq = get_student_lesson_progress_fields(uid, org_id, category_id, week_doc_id)
    qt = int(pq.get("quiz_total") or 0)
    if qt <= 0:
        return
    if int(pq.get("quiz_attempt_count") or 0) > 0:
        return
    qc = int(pq.get("quiz_correct") or 0)
    merge_student_lesson_quiz_result(
        uid,
        org_id,
        category_id,
        week_doc_id,
        quiz_correct=qc,
        quiz_total=qt,
        quiz_passed=bool(pq.get("quiz_passed")),
        quiz_wrong_indices=list(pq.get("quiz_wrong_indices") or []),
    )


def _render_quiz_exam_fullpage(
    *,
    uid: str,
    org_id: str,
    category_id: str,
    course_title: str,
    week: dict[str, Any],
) -> None:
    """객관식 퀴즈 전용 전체 화면(시험장·답안지 스타일). 단계: solve → result → review."""
    _inject_quiz_exam_css()
    wid = str(week.get("_doc_id") or "").strip()
    if not wid or not uid:
        return

    marks = ("①", "②", "③", "④")
    step_key = f"stu_quiz_step_{wid}"
    active_key = f"stu_quiz_active_{wid}"

    ix_key = f"stu_quiz_pool_indices_{wid}"

    def _back_to_week_list() -> None:
        st.session_state.pop(STUDENT_QUIZ_WEEK_ID, None)
        st.session_state.pop(f"stu_quiz_started_{wid}", None)
        st.session_state.pop(f"stu_quiz_last_ans_{wid}", None)
        st.session_state.pop(step_key, None)
        st.session_state.pop(active_key, None)
        st.session_state.pop(f"stu_quiz_buf_{wid}", None)
        st.session_state.pop(f"stu_quiz_buf_sync_{wid}", None)
        st.session_state.pop(ix_key, None)
        st.session_state[STUDENT_VIEW_TAB] = "course"
        st.session_state[STUDENT_COURSE_SUB_TAB] = "learn"
        st.switch_page("pages/5_Student.py")

    widx = int(week.get("week_index") or 0)
    week_title = str(week.get("title") or f"{widx}주차")

    b1, b2 = st.columns([1, 4])
    with b1:
        if st.button("← 주차 목록", key=f"stu_quiz_back_{wid}", use_container_width=True):
            _back_to_week_list()
    with b2:
        st.caption(
            "풀이 중 선택한 답은 이 브라우저에만 유지됩니다. **정답 확인**을 누르면 채점 결과가 서버에 저장됩니다."
        )

    qmode = str(week.get("quiz_mode") or "off")
    if qmode == "off":
        st.warning("이 주차는 퀴즈가 꺼져 있습니다.")
        if st.button("돌아가기", key=f"stu_quiz_off_{wid}"):
            _back_to_week_list()
        return

    prog = get_student_lesson_progress_fields(uid, org_id, category_id, wid)
    pct = int(prog.get("progress_percent") or 0)

    pool = quiz_pool_for_week(week)
    want = quiz_want_count(week)
    tq_prog = int(prog.get("quiz_total") or 0)
    saved_pi = parse_quiz_pool_indices_saved(prog.get("quiz_pool_indices"), len(pool))

    if tq_prog > 0 and len(saved_pi) == tq_prog:
        session = [pool[i] for i in saved_pi if 0 <= i < len(pool)]
        if len(session) != tq_prog:
            session, _ = quiz_session_params(week)
    elif tq_prog > 0:
        session, _ = quiz_session_params(week)
    else:
        if ix_key not in st.session_state:
            st.session_state[ix_key] = draw_quiz_pool_indices(
                len(pool), want, random.Random()
            )
        indices = parse_quiz_pool_indices_saved(st.session_state.get(ix_key), len(pool))
        need_len = min(want, len(pool)) if pool else 0
        if need_len > 0 and (not indices or len(indices) != need_len):
            st.session_state[ix_key] = draw_quiz_pool_indices(
                len(pool), want, random.Random()
            )
            indices = parse_quiz_pool_indices_saved(st.session_state[ix_key], len(pool))
        session = [pool[i] for i in indices]

    pass_min = quiz_pass_min_for_session(week, len(session))

    if not session:
        st.error("풀 수 있는 문항이 없습니다. 교사에게 문의하세요.")
        if st.button("주차 목록으로", key=f"stu_quiz_empty_{wid}"):
            _back_to_week_list()
        return
    unlocked = (qmode == "open_anytime") or (qmode == "after_video" and pct >= 100)
    if not unlocked:
        st.warning("이 퀴즈는 **영상 시청 진행률 100%** 이후에 응시할 수 있습니다.")
        st.progress(min(100, max(0, pct)) / 100.0)
        st.caption(f"현재 진행률: **{pct}%**")
        if st.button("주차 목록으로", key=f"stu_quiz_lock_{wid}"):
            _back_to_week_list()
        return

    tq = tq_prog
    if step_key not in st.session_state:
        st.session_state[step_key] = "result" if tq > 0 else "solve"
    step = str(st.session_state.get(step_key) or "solve")
    if step not in ("solve", "result", "review"):
        step = "solve"
        st.session_state[step_key] = step
    if tq > 0 and step == "solve":
        st.session_state[step_key] = "result"
        step = "result"

    ct = html.escape(course_title or "수업")[:80]
    wt = html.escape(week_title)[:120]

    def _exam_header(*, elapsed_label: str | None = None) -> None:
        el = elapsed_label or "—"
        st.markdown(
            f"""
<div style="background:linear-gradient(180deg,#0d2d5a 0%,#154a8c 100%);color:#fff;padding:1rem 1.35rem 1.15rem 1.35rem;border-radius:10px;margin-bottom:0.85rem;border:1px solid #0a2448;">
  <div style="font-size:0.72rem;opacity:0.88;letter-spacing:0.12em;text-transform:uppercase;">Korean Exam Style · OMR</div>
  <div style="font-size:1.42rem;font-weight:800;margin:0.4rem 0 0.2rem 0;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;">{ct}</div>
  <div style="font-size:0.98rem;opacity:0.95;">{wt}</div>
  <div style="display:flex;flex-wrap:wrap;gap:1rem;margin-top:0.65rem;font-size:0.88rem;opacity:0.92;">
    <span>문항 수 <strong>{len(session)}</strong></span>
    <span>합격 기준 <strong>{pass_min}</strong>개 이상 정답</span>
    <span>경과 <strong>{el}</strong></span>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

    cor_cnt = int(prog.get("quiz_correct") or 0)
    passed = bool(prog.get("quiz_passed"))

    if step == "result":
        _sync_quiz_attempt_if_needed(uid, org_id, category_id, wid)
        _exam_header(elapsed_label="—")
        bar_color = "#145a46" if passed else "#6b2c2c"
        st.markdown(
            f"""
<div style="background:linear-gradient(180deg,{bar_color} 0%,#1a1a1a22 100%);color:#fff;padding:1.1rem 1.25rem;border-radius:10px;margin:0.5rem 0 1rem 0;border:1px solid rgba(255,255,255,0.2);">
  <div style="font-size:0.82rem;opacity:0.92;">제출 완료 · 채점 결과</div>
  <div style="font-size:1.45rem;font-weight:800;margin:0.4rem 0 0.25rem 0;">{'합격' if passed else '불합격'}</div>
  <div style="font-size:1.05rem;line-height:1.55;">
    <strong>{cor_cnt}</strong> / <strong>{tq}</strong> 문항 정답 · 합격 기준은 정답 <strong>{pass_min}</strong>개 이상입니다.
  </div>
  <div style="font-size:0.95rem;opacity:0.95;margin-top:0.5rem;">
    {'축하합니다. 합격 기준을 충족했습니다.' if passed else '합격 기준에 도달하지 못했습니다. 재시도하거나 정답·해설을 확인해 보세요.'}
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        r1, r2, r3 = st.columns(3)
        with r1:
            if st.button("재시도", key=f"stu_quiz_retry_{wid}", use_container_width=True):
                _sync_quiz_attempt_if_needed(uid, org_id, category_id, wid)
                reset_student_lesson_quiz_progress(uid, org_id, category_id, wid)
                for j in range(len(session)):
                    st.session_state.pop(f"stu_q_{wid}_{j}", None)
                st.session_state.pop(f"stu_quiz_last_ans_{wid}", None)
                st.session_state.pop(f"stu_quiz_started_{wid}", None)
                st.session_state.pop(f"stu_quiz_buf_{wid}", None)
                st.session_state.pop(f"stu_quiz_buf_sync_{wid}", None)
                st.session_state.pop(ix_key, None)
                st.session_state[active_key] = 0
                st.session_state[step_key] = "solve"
                st.rerun()
        with r2:
            if st.button("정답 보기", key=f"stu_quiz_to_review_{wid}", use_container_width=True):
                _sync_quiz_attempt_if_needed(uid, org_id, category_id, wid)
                st.session_state[step_key] = "review"
                st.rerun()
        with r3:
            if st.button("주차 목록", key=f"stu_quiz_result_to_list_{wid}", use_container_width=True):
                _back_to_week_list()
        return

    if step == "review":
        _exam_header(elapsed_label="—")
        st.markdown("**정답·해설** — 지문·선택은 항상 보이고, **오른쪽 해설**만 펼쳐 확인할 수 있습니다.")
        _saved = st.session_state.get(f"stu_quiz_last_ans_{wid}")
        if isinstance(_saved, list) and len(_saved) == len(session):
            answers_last = [int(x) for x in _saved]
            _has_my = True
        else:
            answers_last = [0] * len(session)
            _has_my = False
            st.info(
                "이 브라우저에 **제출한 답안 기록**이 없어, 정답·해설만 표시합니다. "
                "(같은 기기에서 제출 직후에는 『내가 선택』도 함께 볼 수 있습니다.)"
            )

        for i, it in enumerate(session):
            opts = list(it.get("options") or [])
            cor_i = int(it.get("correct") or 0)
            my_i = answers_last[i] if i < len(answers_last) else 0
            ok_i = _has_my and (my_i == cor_i)
            exp = str(it.get("explanation") or "").strip()
            if _has_my:
                badge = "정답" if ok_i else "오답"
            else:
                badge = "정답 확인"
            st.markdown("---")
            c_main, c_exp = st.columns([2.1, 1])
            with c_main:
                st.markdown(f"#### 문항 {i + 1} · **{badge}**")
                st.write(f"**지문:** {str(it.get('text') or '')}")
                st.markdown(
                    f"**정답:** {marks[cor_i]} {opts[cor_i] if cor_i < len(opts) else ''}"
                )
                if _has_my:
                    st.markdown(
                        f"**내가 선택:** {marks[my_i]} {opts[my_i] if my_i < len(opts) else ''}"
                    )
                else:
                    st.caption(
                        "『내가 선택』은 이 브라우저에서 **방금 제출한 답안**이 있을 때만 표시됩니다."
                    )
            with c_exp:
                with st.expander(f"해설 · {i + 1}번", expanded=False):
                    if exp:
                        st.info(exp)
                    else:
                        st.caption(
                            "등록된 해설이 없습니다. (교사·AI 출제 시 해설을 넣으면 여기에 표시됩니다.)"
                        )
        b1, b2 = st.columns(2)
        with b1:
            if st.button("결과 화면으로", key=f"stu_quiz_review_back_{wid}", use_container_width=True):
                st.session_state[step_key] = "result"
                st.rerun()
        with b2:
            if st.button("주차 목록", key=f"stu_quiz_review_list_{wid}", use_container_width=True):
                _back_to_week_list()
        return

    # --- solve ---
    tkey = f"stu_quiz_started_{wid}"
    if tkey not in st.session_state:
        st.session_state[tkey] = time.time()
    elapsed = int(time.time() - float(st.session_state.get(tkey) or time.time()))
    em, es = elapsed // 60, elapsed % 60
    _exam_header(elapsed_label=f"{em:02d}:{es:02d}")

    for j in range(len(session)):
        st.session_state.setdefault(f"stu_q_{wid}_{j}", 0)

    st.caption(
        "문항은 **탭**으로 이동합니다. 각 문항마다 선택이 **별도 키**로 저장되어 이전 문항이 초기화되지 않습니다."
    )

    main_c, nav_c = st.columns([3.1, 1])
    with nav_c:
        st.markdown("### 문항·선택 요약")
        st.caption("탭에서 풀이 · 여기서 현재 고른 보기 확인")
        for i in range(len(session)):
            sel = int(st.session_state.get(f"stu_q_{wid}_{i}") or 0)
            sel_l = marks[sel] if 0 <= sel < 4 else "—"
            st.caption(f"**{i + 1}번** {sel_l}")
    with main_c:
        tab_labels = [f"{i + 1}번" for i in range(len(session))]
        tabs = st.tabs(tab_labels)
        for i, tab in enumerate(tabs):
            with tab:
                it = session[i]
                opts = list(it.get("options") or [])
                qbody = html.escape(str(it.get("text") or ""))
                st.markdown(
                    f'<div class="exam-paper"><div class="exam-qhead"><span class="exam-qno">{i + 1}</span>'
                    f'<div style="flex:1;font-size:1.02rem;line-height:1.55;color:#1a1a1a;">{qbody}</div></div>',
                    unsafe_allow_html=True,
                )
                st.radio(
                    "답안 선택",
                    options=[0, 1, 2, 3],
                    format_func=lambda j, m=marks, o=opts: f"{m[j]}  {o[j]}" if j < len(o) else f"{m[j]}",
                    key=f"stu_q_{wid}_{i}",
                    horizontal=True,
                    label_visibility="collapsed",
                )
                st.markdown("</div>", unsafe_allow_html=True)

    sub_a, sub_b = st.columns([2, 1])
    with sub_a:
        if st.button(
            "정답 확인",
            key=f"stu_quiz_submit_{wid}",
            type="primary",
            use_container_width=True,
        ):
            answers = [int(st.session_state.get(f"stu_q_{wid}_{j}") or 0) for j in range(len(session))]
            correct = sum(
                1
                for j, item in enumerate(session)
                if answers[j] == int(item.get("correct") or 0)
            )
            wrong_indices = [
                j
                for j, item in enumerate(session)
                if answers[j] != int(item.get("correct") or 0)
            ]
            passed_sub = correct >= pass_min
            st.session_state[f"stu_quiz_last_ans_{wid}"] = list(answers)
            raw_pool_ix = st.session_state.get(ix_key)
            qpi: list[int] = []
            if isinstance(raw_pool_ix, list):
                for x in raw_pool_ix:
                    try:
                        qpi.append(int(x))
                    except (TypeError, ValueError):
                        pass
            merge_student_lesson_quiz_result(
                uid,
                org_id,
                category_id,
                wid,
                quiz_correct=correct,
                quiz_total=len(session),
                quiz_passed=passed_sub,
                quiz_wrong_indices=wrong_indices,
                quiz_pool_indices=qpi if qpi else None,
            )
            st.session_state[step_key] = "result"
            try:
                st.toast(
                    "채점 결과가 제출·저장되었습니다."
                    + (" 합격입니다." if passed_sub else " 합격 기준에 미달했습니다."),
                    icon="✅" if passed_sub else "📋",
                )
            except Exception:
                pass
            st.rerun()
    with sub_b:
        if st.button("응시 취소", key=f"stu_quiz_cancel_{wid}", use_container_width=True):
            st.session_state.pop(f"stu_quiz_started_{wid}", None)
            _back_to_week_list()


def _render_week_list(
    *,
    uid: str,
    org_id: str,
    category_id: str,
    weeks: list[dict[str, Any]],
    current_id: str | None,
) -> None:
    weeks_shown = [w for w in weeks if week_in_student_list(w)]
    st.markdown(f"##### 주차별 수업 ({len(weeks_shown)}개)")
    st.caption(
        "각 주차의 공개·기간 설정에 따라 **비공개**일 수 있습니다. "
        "**비활성(표시)** 는 목록에 보이나 수강 버튼이 비활성입니다. "
        "**비활성(숨김)** 은 목록에 나오지 않습니다. "
        "**수강 중**은 열람 가능한 주차 중 진행 순서가 가장 뒤인 회차입니다. "
        "진행률 **100%**이면 배지가 **수강완료**로 표시됩니다. "
        "진행률은 시청 기록이 저장되면 반영됩니다."
    )
    if not weeks_shown:
        st.info("표시할 주차가 없습니다. (모든 회차가 숨김 처리되었을 수 있습니다.)")
        return
    for i, w in enumerate(weeks_shown, start=1):
        wid = str(w.get("_doc_id") or "").strip()
        wi = int(w.get("week_index") or 0)
        label_week = wi if wi > 0 else i
        raw_title = str(w.get("title") or "").strip()
        title = _display_week_title_for_student(raw_title, label_week)
        kw = str(w.get("keywords_extracted") or "").strip()
        ok, _ = week_is_visible_to_student(w)
        pct = 0
        prog: dict[str, Any] = {}
        if uid and wid:
            prog = get_student_lesson_progress_fields(uid, org_id, category_id, wid)
            pct = int(prog.get("progress_percent") or 0)
        badge, hint = _week_status_label(
            week=w,
            current_id=current_id,
            progress_pct=pct if ok else None,
        )

        with st.container():
            row_l, row_r = st.columns([3, 1])
            with row_l:
                st.markdown(f"**{label_week}.** {title}")
                if kw:
                    st.markdown(f"**키워드:** {kw}")
                else:
                    st.caption("키워드: 등록된 키워드가 없습니다.")
                qmode = str(w.get("quiz_mode") or "off")
                qsrc = str(w.get("quiz_source") or "manual")
                n_sess, pass_need = (
                    quiz_preview_session_pair(w) if qmode != "off" else (0, 0)
                )
                if qmode == "off":
                    st.caption("퀴즈: 없음")
                elif n_sess == 0:
                    st.caption("퀴즈: 있음 · 문항 **미등록** (교사 설정 필요)")
                else:
                    src_lab = "Gemini" if qsrc == "gemini" else "교사 출제"
                    mode_lab = (
                        "처음부터 풀기"
                        if qmode == "open_anytime"
                        else "영상 100% 후 풀기"
                    )
                    st.caption(
                        f"퀴즈: **있음** · {mode_lab} · {src_lab} · "
                        f"**{n_sess}**문항 · 통과 **{pass_need}**정답 이상"
                    )
                st.caption(hint)
                st.markdown(f"**현재 수강 진행률** {pct}%")
                st.progress(min(100, max(0, pct)) / 100.0)
            with row_r:
                if badge == "비활성":
                    st.warning(badge)
                elif badge == "비공개":
                    st.error(badge)
                elif badge == "수강 중":
                    st.success(badge)
                elif badge == "수강완료":
                    st.success(badge)
                else:
                    st.info(badge)
                clicked = st.button(
                    "수강 듣기",
                    key=f"stu_open_week_{category_id}_{i}_{wid or 'noid'}",
                    type="primary",
                    use_container_width=True,
                    disabled=not ok,
                )
                if clicked and ok:
                    st.session_state.pop(STUDENT_QUIZ_WEEK_ID, None)
                    st.session_state[STUDENT_LEARN_WEEK_ID] = wid
                    st.rerun()
                q_ok = qmode != "off" and n_sess > 0
                unlock_q = ok and q_ok and (
                    (qmode == "open_anytime")
                    or (qmode == "after_video" and pct >= 100)
                )
                q_done = bool(prog.get("quiz_passed"))
                if q_ok:
                    if q_done:
                        st.caption("퀴즈 완료 ✓")
                    else:
                        if st.button(
                            "퀴즈 풀기",
                            key=f"stu_quiz_open_{category_id}_{i}_{wid or 'noid'}",
                            use_container_width=True,
                            disabled=not unlock_q,
                        ):
                            st.session_state[STUDENT_QUIZ_WEEK_ID] = wid
                            st.rerun()
                    if not unlock_q and ok and qmode == "after_video":
                        st.caption("영상 100% 시 퀴즈 열림")
        st.divider()


def _render_learn_right_sidebar(
    *,
    org_id: str,
    category_id: str,
    week_doc_id: str,
    title: str,
    goals: str,
    preview: str,
    keywords: str,
    live_on: bool,
    week_index: int = 0,
) -> None:
    """상단: 사이드바 톤 버튼(모드) → 중앙: 고정 높이 스크롤 영역 → 하단: 입력."""
    mode_key = f"stu_learn_mode_{week_doc_id}"
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "ai"
    mode = str(st.session_state.get(mode_key) or "ai")
    if mode not in ("live", "ai", "overview"):
        mode = "ai"
        st.session_state[mode_key] = mode

    st.markdown("###### 목록")
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button(
            "라이브 채팅",
            key=f"stu_mode_live_{week_doc_id}",
            type="primary" if mode == "live" else "secondary",
            use_container_width=True,
        ):
            st.session_state[mode_key] = "live"
    with b2:
        if st.button(
            "AI 채팅",
            key=f"stu_mode_ai_{week_doc_id}",
            type="primary" if mode == "ai" else "secondary",
            use_container_width=True,
        ):
            st.session_state[mode_key] = "ai"
    with b3:
        if st.button(
            "수업 개요",
            key=f"stu_mode_ov_{week_doc_id}",
            type="primary" if mode == "overview" else "secondary",
            use_container_width=True,
        ):
            st.session_state[mode_key] = "overview"

    st.divider()

    if mode == "overview":
        st.markdown("###### 이번 주차 안내")
        _render_overview_scroll_html(
            title=title,
            goals=goals,
            preview=preview,
            keywords=keywords,
            height_px=320,
        )
        return

    st.markdown("###### 채팅창")

    if mode == "live":
        if not live_on:
            st.caption("🔒 라이브 세션이 아닐 때는 채팅이 잠깁니다.")
            st.info(
                "교사가 **라이브 세션**을 켠 경우에만 실시간 채팅을 사용할 수 있습니다."
            )
            _render_scrollable_chat_html([], height_px=180)
            st.divider()
            st.caption("채팅 입력칸")
            st.text_input(
                "메시지",
                placeholder="라이브가 켜지면 입력할 수 있습니다",
                disabled=True,
                key=f"stu_live_disabled_{week_doc_id}",
                label_visibility="collapsed",
            )
            return

        st.caption("라이브 세션이 활성화되었습니다. (데모: 이 브라우저에만 저장됩니다.)")
        mk = f"stu_live_{org_id}_{category_id}_{week_doc_id}"
        st.session_state.setdefault(mk, [])
        live_chat_ph = st.empty()
        st.divider()
        st.caption("채팅 입력칸")
        with st.form(f"live_form_{week_doc_id}", clear_on_submit=True):
            live_in = st.text_input(
                "메시지",
                placeholder="메시지를 입력하세요",
                label_visibility="collapsed",
            )
            live_sub = st.form_submit_button("전송", use_container_width=True)
        if live_sub and (live_in or "").strip():
            msgs = list(st.session_state[mk])
            msgs.append({"role": "user", "content": live_in.strip()})
            msgs.append(
                {
                    "role": "assistant",
                    "content": "(데모) 강사 측 연동 전까지 메시지가 로컬에만 쌓입니다.",
                }
            )
            st.session_state[mk] = msgs
        msgs = st.session_state[mk]
        with live_chat_ph.container():
            _render_scrollable_chat_html(msgs, height_px=320)
        return

    # AI 채팅
    st.caption("이번 주차 학습 목표·요약을 바탕으로 질문할 수 있습니다.")
    if not gemini_client.get_api_key():
        ui_messages.warn_gemini_key_missing()
        _render_scrollable_chat_html([], height_px=220)
        st.divider()
        st.caption("채팅 입력칸")
        st.text_input(
            "질문",
            placeholder="API 키 설정 후 이용 가능",
            disabled=True,
            key=f"stu_ai_disabled_{week_doc_id}",
            label_visibility="collapsed",
        )
        return

    ak = f"stu_ai_{org_id}_{category_id}_{week_doc_id}"
    st.session_state.setdefault(ak, [])
    ai_chat_ph = st.empty()
    st.divider()
    st.caption("채팅 입력칸")
    with st.form(f"ai_form_{week_doc_id}", clear_on_submit=True):
        q_in = st.text_input(
            "질문",
            placeholder="이번 주차 내용에 대해 질문하세요",
            label_visibility="collapsed",
        )
        ai_sub = st.form_submit_button("질문하기", use_container_width=True)
    if ai_sub:
        q_text = (q_in or "").strip()
        if q_text:
            hist = list(st.session_state[ak])
            hist.append({"role": "user", "content": q_text})
            uid = str(st.session_state.get(AUTH_UID) or "").strip()
            try:
                ans = gemini_client.answer_student_lesson_question(
                    question=q_text,
                    title=title,
                    learning_goals=goals,
                    summary=preview,
                    keywords=keywords,
                    usage={
                        "org_id": org_id,
                        "category_id": category_id,
                        "bucket": "student_chat",
                        "usage_kind": "student_week_ai_chat",
                    },
                )
                hist.append({"role": "assistant", "content": ans})
                if uid:
                    try:
                        append_student_lesson_question(
                            org_id,
                            category_id,
                            week_doc_id,
                            uid,
                            q_text,
                            ans,
                            week_title=title,
                            week_index=week_index,
                            student_email=str(st.session_state.get(AUTH_EMAIL) or ""),
                            display_name=str(st.session_state.get(AUTH_DISPLAY_NAME) or ""),
                        )
                    except Exception:
                        pass
            except Exception as e:
                err_txt = gemini_client.format_quota_error_message(e)
                hist.append({"role": "assistant", "content": err_txt})
                if uid:
                    try:
                        append_student_lesson_question(
                            org_id,
                            category_id,
                            week_doc_id,
                            uid,
                            q_text,
                            err_txt,
                            week_title=title,
                            week_index=week_index,
                            student_email=str(st.session_state.get(AUTH_EMAIL) or ""),
                            display_name=str(st.session_state.get(AUTH_DISPLAY_NAME) or ""),
                        )
                    except Exception:
                        pass
            st.session_state[ak] = hist

    hist = st.session_state[ak]
    with ai_chat_ph.container():
        _render_scrollable_chat_html(hist, height_px=320)


def _render_learn_player(
    *,
    uid: str,
    org_id: str,
    category_id: str,
    week_doc_id: str,
) -> None:
    st.session_state.pop(STUDENT_QUIZ_WEEK_ID, None)

    week = get_lesson_week(org_id, category_id, week_doc_id)
    if not week:
        st.error("주차 정보를 불러올 수 없습니다.")
        if st.button("← 주차 목록", key="stu_back_invalid"):
            st.session_state[STUDENT_VIEW_TAB] = "course"
            st.session_state[STUDENT_COURSE_SUB_TAB] = "learn"
            st.session_state.pop(STUDENT_LEARN_WEEK_ID, None)
            st.switch_page("pages/5_Student.py")
        return

    ok, reason = week_is_visible_to_student(week)
    if not ok:
        st.warning(reason or "이 회차는 열람할 수 없습니다.")
        if st.button("← 주차 목록", key="stu_back_locked"):
            st.session_state[STUDENT_VIEW_TAB] = "course"
            st.session_state[STUDENT_COURSE_SUB_TAB] = "learn"
            st.session_state.pop(STUDENT_LEARN_WEEK_ID, None)
            st.switch_page("pages/5_Student.py")
        return

    _inject_learn_player_css()

    widx = int(week.get("week_index") or 0)
    title = str(week.get("title") or f"{widx}주차")
    goals = str(week.get("learning_goals") or "")
    preview = str(week.get("ai_summary_preview") or "")
    keywords = str(week.get("keywords_extracted") or "")
    video_url = str(week.get("lesson_video_url") or "").strip()
    live_on = bool(week.get("live_session_active"))

    panel_key = f"stu_learn_panel_{category_id}_{week_doc_id}"
    st.session_state.setdefault(panel_key, True)

    _fr = _streamlit_fragment_decorator()

    if st.button("← 수업 목록으로", key="stu_back_list"):
        st.session_state[STUDENT_VIEW_TAB] = "course"
        st.session_state[STUDENT_COURSE_SUB_TAB] = "learn"
        st.session_state.pop(STUDENT_LEARN_WEEK_ID, None)
        st.switch_page("pages/5_Student.py")

    # 영상은 fragment 밖(왼쪽 열)에만 두어 우측 패널 토글 시 components.html 이 재마운트되지 않게 함.
    def _learn_right_panel_body() -> None:
        open_now = bool(st.session_state.get(panel_key))
        st.markdown(_player_column_resize_css(open_now), unsafe_allow_html=True)
        if st.button(
            "우측 패널 접기" if open_now else "우측 패널 펼치기",
            key="stu_toggle_side_panel",
            use_container_width=True,
        ):
            st.session_state[panel_key] = not open_now
            open_now = bool(st.session_state.get(panel_key))
            if _fr is None:
                st.rerun()
        if open_now:
            _render_learn_right_sidebar(
                org_id=org_id,
                category_id=category_id,
                week_doc_id=week_doc_id,
                title=title,
                goals=goals,
                preview=preview,
                keywords=keywords,
                live_on=live_on,
                week_index=widx,
            )

    st.markdown(
        _player_column_resize_css(bool(st.session_state.get(panel_key))),
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.72, 0.78], gap="small")
    with left:
        st.markdown("###### 영상")
        _render_video_area(
            video_url,
            progress_uid=uid,
            org_id=org_id,
            category_id=category_id,
            week_doc_id=week_doc_id,
        )
    with right:
        if _fr is not None:
            _fr(_learn_right_panel_body)()
        else:
            _learn_right_panel_body()


def render_student_course_learn(
    *,
    org_id: str,
    category_id: str,
) -> None:
    _reset_learn_player_if_course_changed(category_id)

    weeks = list_lesson_weeks(org_id, category_id)
    if not weeks:
        st.warning("이 수업에 등록된 주차가 없습니다.")
        return

    cw = pick_current_week_for_student(weeks)
    current_id = str(cw.get("_doc_id") or "") if cw else None

    uid = str(st.session_state.get(AUTH_UID) or "")
    cat = get_content_category(org_id, category_id) or {}
    course_title = str(cat.get("name") or cat.get("title") or "수업")

    playing = st.session_state.get(STUDENT_LEARN_WEEK_ID)
    playing_str = str(playing).strip() if playing else ""
    ids = {str(w.get("_doc_id") or "") for w in weeks if w.get("_doc_id")}

    quiz_wid = str(st.session_state.get(STUDENT_QUIZ_WEEK_ID) or "").strip()
    if quiz_wid and quiz_wid not in ids:
        st.session_state.pop(STUDENT_QUIZ_WEEK_ID, None)
        quiz_wid = ""

    if quiz_wid and quiz_wid in ids:
        wq = get_lesson_week(org_id, category_id, quiz_wid)
        if wq:
            _render_quiz_exam_fullpage(
                uid=uid,
                org_id=org_id,
                category_id=category_id,
                course_title=course_title,
                week=wq,
            )
        else:
            st.error("퀴즈 주차를 불러올 수 없습니다.")
            if st.button("주차 목록으로", key="stu_quiz_missing_week"):
                st.session_state.pop(STUDENT_QUIZ_WEEK_ID, None)
                st.switch_page("pages/5_Student.py")
        return

    if playing_str and playing_str in ids:
        _render_learn_player(
            uid=uid,
            org_id=org_id,
            category_id=category_id,
            week_doc_id=playing_str,
        )
        return

    if playing_str:
        st.session_state.pop(STUDENT_LEARN_WEEK_ID, None)

    _render_week_list(
        uid=uid,
        org_id=org_id,
        category_id=category_id,
        weeks=weeks,
        current_id=current_id,
    )
