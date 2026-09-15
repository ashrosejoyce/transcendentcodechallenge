from app.rag.chunking import chunk_text


def test_short_text_is_a_single_chunk():
    assert chunk_text("A short post.", max_chars=800) == ["A short post."]


def test_empty_text_returns_no_chunks():
    assert chunk_text("   ", max_chars=800) == []


def test_long_text_is_split_into_multiple_chunks():
    paragraph = "This is a beekeeping sentence about hive health. " * 40
    chunks = chunk_text(paragraph, max_chars=200, overlap_chars=20)
    assert len(chunks) > 1
    # each chunk is at most max_chars, plus a bit of overlap context carried
    # over from the previous chunk (an overlap tail + one joining space)
    assert all(len(chunk) <= 200 + 20 + 1 for chunk in chunks)


def test_chunks_preserve_all_words_at_least_once():
    text = "alpha beta gamma delta epsilon " * 30
    chunks = chunk_text(text, max_chars=100, overlap_chars=10)
    combined = " ".join(chunks)
    for word in ["alpha", "beta", "gamma", "delta", "epsilon"]:
        assert word in combined


def test_paragraphs_are_kept_together_when_they_fit():
    text = "Paragraph one.\nParagraph two.\nParagraph three."
    chunks = chunk_text(text, max_chars=800)
    assert len(chunks) == 1
    assert "Paragraph one." in chunks[0]
    assert "Paragraph three." in chunks[0]
