"""Manual Phase 2 verification helper — not part of production CLI."""

import sqlite3
import subprocess
import sys
from pathlib import Path

REASONS = ["network_timeout", "insufficient_funds", "expired_card", "repeated_failure"]
DB = Path(__file__).resolve().parents[1] / "data" / "podium.db"


def main() -> None:
    conn = sqlite3.connect(DB)
    for reason in REASONS:
        row = conn.execute(
            """
            SELECT case_id FROM recovery_cases
            WHERE lane = 'subscription_payment' AND failure_reason = ?
            LIMIT 1
            """,
            (reason,),
        ).fetchone()
        case_id = row[0]
        # Demo fixture: reset case + customer contact state for clean simulation
        subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sqlite3; from podium.state.reset import reset_case_for_run; "
                f"c=sqlite3.connect(r'{DB}'); reset_case_for_run(c, '{case_id}'); "
                f"r=c.execute('SELECT customer_id FROM recovery_cases WHERE case_id=?', ('{case_id}',)).fetchone(); "
                f"c.execute('UPDATE customers SET opt_out=0, prior_contacts_7d=0 WHERE customer_id=?', (r[0],)); "
                f"c.commit(); c.close()",
            ],
            cwd=DB.parent.parent,
            check=True,
        )
        print("=" * 60)
        print(f"{reason} -> {case_id}")
        print("=" * 60)
        subprocess.run(
            [sys.executable, "scripts/run_case.py", "--case-id", case_id],
            cwd=DB.parent.parent,
            check=False,
        )
    conn.close()


if __name__ == "__main__":
    main()
