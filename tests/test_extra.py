from chronoscope.core.extra import dump_extra, flatten_extra, load_extra


def test_extra_roundtrip():
    d = {"url": "https://x/", "count": 3, "tags": ["a", "b"], "nested": {"k": 1}}
    blob = dump_extra(d)
    assert isinstance(blob, bytes)
    assert load_extra(blob) == d


def test_extra_empty_dict_encodes_to_small_blob():
    blob = dump_extra({})
    assert load_extra(blob) == {}


def test_extra_handles_non_string_keys_by_coercing():
    blob = dump_extra({"x": 1})
    assert load_extra(blob) == {"x": 1}


def test_flatten_extra_includes_keys_and_values():
    s = flatten_extra({"url": "https://example.com/", "visit_count": 3})
    assert "url" in s
    assert "https://example.com/" in s
    assert "visit_count" in s
    assert "3" in s


def test_flatten_extra_walks_nested_dicts_and_lists():
    s = flatten_extra({"outer": {"inner": "secret"}, "tags": ["alpha", "beta"]})
    assert "secret" in s
    assert "alpha" in s
    assert "beta" in s


def test_flatten_extra_handles_none_and_bytes():
    s = flatten_extra({"missing": None, "blob": b"\xde\xad"})
    assert "dead" in s
    assert "missing" in s


def test_flatten_extra_empty_dict():
    assert flatten_extra({}) == ""
