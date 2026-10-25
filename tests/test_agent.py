import plistlib
import xml.etree.ElementTree as ET

from sawt import agent, paths

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def test_launchd_plist_keeps_serve_alive():
    p = plistlib.loads(agent.plist_text().encode())
    assert p["ProgramArguments"][-3:] == ["-m", "sawt", "serve"]
    assert p["RunAtLoad"] and p["KeepAlive"]
    assert p["EnvironmentVariables"]["SAWT_HOME"] == str(paths.ROOT)


def test_systemd_unit_restarts_and_starts_at_login():
    unit = agent.unit_text()
    assert "-m sawt serve" in unit
    assert "Restart=always" in unit
    assert "WantedBy=default.target" in unit
    assert f'Environment="SAWT_HOME={paths.ROOT}"' in unit


def test_windows_task_runs_hidden_at_logon_and_restarts():
    root = ET.fromstring(agent.task_xml().split("\n", 1)[1])   # drop the UTF-16 declaration
    assert root.find("t:Triggers/t:LogonTrigger", NS) is not None
    assert root.find("t:Actions/t:Exec/t:Arguments", NS).text == "-m sawt serve"
    assert root.find("t:Settings/t:ExecutionTimeLimit", NS).text == "PT0S"   # no time limit
    assert root.find("t:Settings/t:RestartOnFailure/t:Count", NS) is not None
