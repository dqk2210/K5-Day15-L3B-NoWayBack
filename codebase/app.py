"""Giao diện dòng lệnh tối thiểu (HITL): gõ đầu vào -> answer() -> bác sĩ duyệt.

Chạy bằng: python run.py
"""

import os
import sys

for _stream in (sys.stdout, sys.stderr, sys.stdin):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _where(e: Exception) -> str:
    import traceback

    path = getattr(e, "filename", None) or (
        traceback.extract_tb(e.__traceback__)[-1].filename if e.__traceback__ else ""
    )
    if not path:
        return "codebase/"
    p = os.path.abspath(path)
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.relpath(p, base).replace(os.sep, "/") if p.startswith(base) else path


def main() -> int:
    try:
        import tracing
        from agent import answer
    except Exception as e:
        print(
            "Không nạp được codebase/ — lỗi ở %s: %s: %s"
            % (_where(e), type(e).__name__, e)
        )
        print("Sửa lỗi rồi chạy lại. Cách nối model: docs/connect-model.md")
        return 1

    print(
        "Bản chạy thử AI Hỗ Trợ Dự Thảo Đơn Thuốc (HITL) — gõ thông tin ca bệnh rồi Enter."
    )
    print("Thoát: Ctrl+C (hoặc Enter 2 lần với dòng trống).")
    blank = 0
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            blank += 1
            if blank >= 2:
                return 0
            continue
        blank = 0
        tracing.begin("app")
        try:
            result = answer(text)
        except NotImplementedError as e:
            tracing.end()
            print("Chưa nối model: %s" % e)
            return 1
        except Exception as e:
            tracing.end()
            print("[lỗi] %s: %s" % (type(e).__name__, e))
            continue
        s, _ = tracing.end()
        output_text = result.get("output", "") if isinstance(result, dict) else str(result)
        print(output_text)
        print(
            "   (model: %s · gọi model %d lần · công cụ %d lần · token vào %d / ra %d)"
            % (
                ", ".join(s["models"]) or "—",
                s["model_calls"],
                s["tool_calls"],
                s["tokens_in"],
                s["tokens_out"],
            )
        )
        if "Quyết định: DRAFT_" in output_text:
            try:
                choice = input(
                    "Bác sĩ kiểm duyệt — [A] Chấp nhận bản nháp / [E] Yêu cầu chỉnh sửa / [R] Từ chối: "
                ).strip().upper()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if choice == "A":
                print("-> Đã ghi nhận bác sĩ CHẤP NHẬN bản nháp (bản mô phỏng, không phát hành đơn thật).")
            elif choice == "E":
                print("-> Chuyển sang chế độ chỉnh sửa: vui lòng nhập lại yêu cầu điều chỉnh.")
            else:
                print("-> Bác sĩ đã TỪ CHỐI bản nháp.")


if __name__ == "__main__":
    sys.exit(main())
