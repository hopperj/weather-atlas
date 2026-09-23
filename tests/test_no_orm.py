from pathlib import Path


def test_application_has_no_direct_orm_dependency() -> None:
    project = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    forbidden = ("sqlalchemy", "django", "prisma", "peewee", "tortoise-orm")
    normalized = project.lower()

    assert not any(f'"{package}' in normalized for package in forbidden)

