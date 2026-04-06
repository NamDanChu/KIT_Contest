"""추상 포트(Protocol) — DIP: UI·도메인은 구체 구현이 아닌 인터페이스에 의존."""

from typing import Protocol


class AuthPort(Protocol):
    """인증 (Firebase Auth 등 구현체로 교체 가능)."""

    def sign_in(self, email: str, password: str) -> str:
        """성공 시 uid 등 식별자 반환."""
        ...

    def sign_out(self) -> None:
        ...


class UserRepositoryPort(Protocol):
    """Users 컬렉션 접근."""

    def get_role(self, uid: str) -> str | None:
        ...
