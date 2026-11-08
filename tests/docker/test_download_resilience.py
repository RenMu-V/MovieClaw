"""Release downloads must retry truncated transfers and verify pinned NER assets."""
from pathlib import Path


def test_release_downloads_retry_all_errors():
    text = (Path(__file__).parents[2] / 'Dockerfile').read_text()
    downloads = [line for line in text.splitlines() if 'curl -fSL --retry' in line]
    assert downloads
    assert all('--retry-all-errors' in line for line in downloads)


def test_ner_release_assets_are_sha256_pinned():
    text = (Path(__file__).parents[2] / 'Dockerfile').read_text()
    for digest in (
        'f59764e2021d0c8dbb84f580916d478a587d44e3f8d7778cbaca31a71a3734a3',
        'a34543f1ac37c19b829db3674d5af635d1d72a5b4b3801d0ba208911df5860a2',
        '86451093d5112802bc19a34675115cf417fb70749df8c2059df98923b605f2ab',
    ):
        assert digest in text
