"""Cloud Firestore — Organizations / Users / ChatLogs CRUD 스텁."""


def get_user_role(uid: str) -> str | None:
    raise NotImplementedError("Firestore 연동 후 구현")


def append_chat_log(uid: str, query: str, answer: str) -> None:
    raise NotImplementedError("Firestore 연동 후 구현")
