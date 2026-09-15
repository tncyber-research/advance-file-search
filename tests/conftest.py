"""Shared fixtures.

Every test runs against a throwaway application data directory so nothing
touches the developer's real index, and every document is synthetic.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_app_data(tmp_path_factory, monkeypatch):
    """Point the application at a temporary data directory for every test."""
    base = tmp_path_factory.mktemp("appdata")
    monkeypatch.setenv("ADVANCE_FILE_SEARCH_DATA_DIR", str(base))
    from advance_file_search.core import paths as pathutil

    pathutil.ensure_app_dirs()
    yield base


@pytest.fixture
def db(tmp_path):
    """A migrated index database in a temporary file."""
    from advance_file_search.storage.migrations import open_index

    database, _migration = open_index(tmp_path / "index.sqlite3")
    yield database
    database.close()


@pytest.fixture
def repos(db):
    from advance_file_search.storage.repositories import Repositories

    return Repositories.create(db)


@pytest.fixture(scope="session")
def fixture_tree(tmp_path_factory) -> Path:
    """Generate the synthetic document fixtures once per test session."""
    from tests.make_fixtures import write_all

    target = tmp_path_factory.mktemp("fixtures")
    write_all(target)
    return target


@pytest.fixture
def corpus(fixture_tree, tmp_path) -> Path:
    """A fresh copy of the fixture tree, safe to mutate in a test."""
    root = tmp_path / "corpus"
    root.mkdir()
    for group in ("txt", "pdf", "docx", "xlsx", "hostile"):
        source = fixture_tree / group
        if source.exists():
            shutil.copytree(source, root / "เอกสาร" / group)
    return root


@pytest.fixture
def settings():
    from advance_file_search.core.settings import AppSettings

    return AppSettings(enable_optional_formats=True).normalize()


@pytest.fixture
def indexed_corpus(repos, corpus, settings):
    """Index ``corpus`` and return ``(root, summary)``."""
    from advance_file_search.indexing.coordinator import IndexCoordinator, IndexOptions

    summary = IndexCoordinator(repos, IndexOptions(settings=settings)).run(str(corpus))
    root = repos.roots.find_by_path(str(corpus))
    assert root is not None
    return root, summary


@pytest.fixture
def search_service(repos):
    from advance_file_search.search.search_service import SearchService

    return SearchService(repos)


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication for the whole session (Qt allows only one)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
