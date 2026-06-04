from lib.replay import make_replay_client, replay_chat_completion


def test_cassette_loaded():
    client = make_replay_client()
    assert client.loaded >= 1


def test_replay_returns_ok():
    content = replay_chat_completion()
    assert content == "REPLAY_OK"
