import argparse
import asyncio
from unittest.mock import AsyncMock, MagicMock

from agents.auditor.continuity_auditor import ContinuityAuditor
from core.bridge.config_manager import ConfigManager
from core.bridge.kimi_bridge import KimiBridge
from core.hermes.hermes_agent import HermesAgent
from core.orchestrator.cinesmith_orchestrator import CinesmithOrchestrator
from core.state.session_manager import SessionManager


async def _run_mock(script_path: str) -> None:
    config = MagicMock(spec=ConfigManager)
    config.get.return_value = {"schema_version": "2.0"}
    kimi = AsyncMock(spec=KimiBridge)
    kimi.direct_with_narrative.return_value = {
        "shots": [
            {"shot_id": "SHOT_001", "description": "A cinematic establishing shot."},
            {"shot_id": "SHOT_002", "description": "A close reaction shot."},
        ],
        "reasoning_trace": "Mocked demo run.",
    }
    auditor = AsyncMock(spec=ContinuityAuditor)
    auditor.audit_asset.return_value = {"is_consistent": True, "confidence_score": 1.0}
    remediation = AsyncMock()
    session = SessionManager("demo_mock_session", output_dir="data/sessions_test")
    hermes = HermesAgent(kimi_bridge=kimi, session_manager=session)
    orchestrator = CinesmithOrchestrator(
        config_manager=config,
        session_manager=session,
        kimi_bridge=kimi,
        hermes_agent=hermes,
        continuity_auditor=auditor,
        remediation_loop=remediation,
    )
    await orchestrator.run(script_path, [])
    print("PRODUCTION COMPLETE")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Cinesmith demo pipeline.")
    parser.add_argument("--script", default="scripts/demo/pilot_script.md")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    if not args.mock:
        raise SystemExit("Only --mock is supported by this lightweight demo entrypoint.")
    asyncio.run(_run_mock(args.script))


if __name__ == "__main__":
    main()
