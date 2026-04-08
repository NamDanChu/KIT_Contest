"""Streamlit session_state 키 상수 — 문자열 흩뿌리기 방지."""

AUTH_UID = "auth_uid"
AUTH_EMAIL = "auth_email"
AUTH_DISPLAY_NAME = "auth_display_name"
AUTH_ROLE = "auth_role"
AUTH_ORG_ID = "auth_org_id"
AUTH_ORG_NAME = "auth_org_name"  # 현재 선택/소속 기업 표시명
MGMT_SELECTED_ORG_ID = "mgmt_selected_org_id"  # 관리 화면에서 선택한 기업
MGMT_VIEW_MODE = "mgmt_view_mode"  # "list" | "detail"
MGMT_DETAIL_TAB = "mgmt_detail_tab"  # basic | plan | people | content | ai_usage
AUTH_ID_TOKEN = "auth_id_token"
AUTH_REFRESH_TOKEN = "auth_refresh_token"
AUTH_VIEW = "auth_view"  # "login" | "signup" | "invite_signup"
CHAT_MESSAGES = "chat_messages"
# 교사: 선택 중인 콘텐츠 카테고리 (ContentCategories 문서 ID)
TEACHER_SELECTED_CATEGORY_ID = "teacher_selected_category_id"
# 교사: 선택한 카테고리 하위 항목 id (sub_items[].id, 없으면 "default")
TEACHER_SELECTED_SUB_ITEM_ID = "teacher_selected_sub_item_id"
# 교사: 본문 탭 — overview | students | course_stats | ai_usage | lesson_mgmt (선택 수업 맥락)
TEACHER_VIEW_TAB = "teacher_view_tab"
# 교사: 수업 선택 변경 감지용 (category_id:sub_item_id)
TEACHER_LESSON_FINGERPRINT = "_teacher_lesson_fp"
# 교사 · 학생 관리 탭: 메인 화면에 상세를 펼칠 학생 UID (비어 있으면 미선택)
TEACHER_STUDENT_DETAIL_UID = "teacher_student_detail_uid"
# 학생: 개요 | 수업 화면 | 통합 퀴즈(연습)
STUDENT_VIEW_TAB = "student_view_tab"  # "overview" | "course" | "quiz_mix"
# 통합 퀴즈: setup | run | done | inf_run(무한 연습 한 문제씩)
STUDENT_QUIZ_MIX_PHASE = "student_quiz_mix_phase"
# 통합 퀴즈 연습 방식: batch(일괄) | infinite(무한·즉시 해설)
STUDENT_QUIZ_MIX_STYLE = "student_quiz_mix_style"
STUDENT_SELECTED_CATEGORY_ID = "student_selected_category_id"
# 학생 수업 화면: 수업 개요 | 수업 수강
STUDENT_COURSE_SUB_TAB = "student_course_sub_tab"  # "overview" | "learn"
# 학생 수업 수강: 주차 플레이어(영상+우측 패널)로 들어간 주차 문서 ID
STUDENT_LEARN_WEEK_ID = "student_learn_week_id"
STUDENT_LEARN_CATEGORY_FP = "student_learn_category_fp"  # course 바뀌면 플레이어 초기화용
# 학생 수업 수강: 주차 목록에서 퀴즈 폼을 펼친 주차 문서 ID (없으면 미표시)
STUDENT_QUIZ_WEEK_ID = "student_quiz_week_id"
