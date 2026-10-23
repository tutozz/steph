from steph import audio


def test_pw_play_reads_raw_pcm_from_stdin(monkeypatch):
    # Without --raw, pw-play waits for a file header on stdin and exits (Solus, no paplay).
    monkeypatch.setattr(audio, "IS_MAC", False)
    monkeypatch.setattr(audio.shutil, "which", lambda name: name == "pw-play")
    cmd = audio.stream_player_cmd(22050)
    assert cmd[0] == "pw-play"
    assert "--raw" in cmd
