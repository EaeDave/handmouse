import os
import textwrap

from handmouse.config import Config, load_config


def test_defaults():
    c = Config()
    assert c.start_paused is True
    assert c.notify is True
    assert c.gain == 2500.0
    assert c.idle_pause_s == 30
    assert c.pinch_open_threshold > c.pinch_close_threshold  # histerese


def test_load_overrides_subset(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent(
            """
            camera_index = 2
            gain = 1234.0
            notify = false
            unknown_key = "ignorado"
            """
        )
    )
    c = load_config(p)
    assert c.camera_index == 2
    assert c.gain == 1234.0
    assert c.notify is False
    assert c.frame_width == 640  # default preservado


def test_missing_file_uses_defaults(tmp_path):
    c = load_config(tmp_path / "nope.toml")
    assert c.camera_index == 0


def test_model_path_is_expanded(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('model_path = "~/x/model.task"\n')
    c = load_config(p)
    assert c.model_path == os.path.expanduser("~/x/model.task")
    assert "~" not in c.model_path
