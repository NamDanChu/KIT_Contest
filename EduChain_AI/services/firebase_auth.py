"""Firebase Auth 연동 스텁. 구현 시 firebase-admin 또는 클라이언트 SDK 사용."""


def sign_in(email: str, password: str) -> str:
    raise NotImplementedError("Firebase Auth 연동 후 구현")


def sign_out() -> None:
    raise NotImplementedError("Firebase Auth 연동 후 구현")
