import os
import textwrap

from handmouse.config import Config, load_config


def test_defaults():
    c = Config()
    assert c.start_paused is True
    assert c.notify is True
    assert c.gain == 2500.0
    assert c.idle_pause_s == 30
    assert c.camera_fps == 30
    assert c.camera_mjpg is True
    assert c.accel is True
    assert c.delegate == "cpu"
    assert c.scroll_enabled is True
    assert c.scroll_dwell_ms == 220
    assert c.scroll_gain == 60.0
    assert c.pinch_open_threshold > c.pinch_close_threshold
    assert c.pinch_close_threshold == 0.18
    assert c.toggle_gesture == "rock"
    assert c.toggle_dwell_ms == 500
    assert c.close_window_gesture == "fist"
    assert c.close_window_dwell_ms == 1000
    assert c.close_window_command == "hyprctl dispatch killactive"


def test_load_overrides_subset(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        textwrap.dedent(
            """
            camera_index = 2
            gain = 1234.0
            notify = false
            accel = false
            delegate = "gpu"
            scroll_enabled = false
            scroll_dwell_ms = 300
            scroll_gain = 80.0
            toggle_dwell_ms = 1800
            close_window_dwell_ms = 3000
            close_window_command = "hyprctl dispatch closewindow"
            unknown_key = "ignorado"
            """
        )
    )
    c = load_config(p)
    assert c.camera_index == 2
    assert c.gain == 1234.0
    assert c.notify is False
    assert c.accel is False
    assert c.delegate == "gpu"
    assert c.scroll_enabled is False
    assert c.scroll_dwell_ms == 300
    assert c.scroll_gain == 80.0
    assert c.toggle_dwell_ms == 1800
    assert c.close_window_dwell_ms == 3000
    assert c.close_window_command == "hyprctl dispatch closewindow"
    assert c.frame_width == 640


def test_missing_file_uses_defaults(tmp_path):
    c = load_config(tmp_path / "nope.toml")
    assert c.camera_index == 0


def test_model_path_is_expanded(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('model_path = "~/x/model.task"\n')
    c = load_config(p)
    assert c.model_path == os.path.expanduser("~/x/model.task")
    assert "~" not in c.model_path
