__version__ = "0.1.0"

from .evolving import evolving, EvolverxConfig
from .persist import get_diff_text, get_diff_paths, clean_cache

__all__ = [
    "evolving",
    "EvolverxConfig",
    "get_diff_text",
    "get_diff_paths",
    "clean_cache",
]


def _main_cli():
    import argparse
    import pathlib
    from .persist import get_diff_text, regenerate_diff_artifacts

    parser = argparse.ArgumentParser(prog="evolverx", description="Evolverx CLI")
    sub = parser.add_subparsers(dest="cmd", required=False)

    # show command (default)
    p_show = sub.add_parser("show", help="Show diff artifacts for a function")
    p_show.add_argument("module", help="Module name of the function, e.g., mypkg.mymod")
    p_show.add_argument("func", help="Function name")
    p_show.add_argument(
        "--cache-dir",
        dest="cache_dir",
        default=None,
        help="Cache directory (defaults to project .evolverx/cache)",
    )
    p_show.add_argument(
        "--show",
        choices=["diff", "md", "html"],
        default="diff",
        help="Which artifact to show (prints path for md/html)",
    )
    p_show.add_argument(
        "--regen", action="store_true", help="Regenerate diff artifacts before showing"
    )

    # clean command
    p_clean = sub.add_parser("clean", help="Clean cache (all or scoped)")
    p_clean.add_argument(
        "--module", help="Module name to clean (optional)", default=None
    )
    p_clean.add_argument(
        "--func",
        help="Function name to clean (optional; requires --module)",
        default=None,
    )
    p_clean.add_argument(
        "--cache-dir",
        dest="cache_dir",
        default=None,
        help="Cache directory (defaults to project .evolverx/cache)",
    )

    args = parser.parse_args()

    cache_dir_str = getattr(args, "cache_dir", None)
    base = (
        pathlib.Path(cache_dir_str)
        if cache_dir_str
        else pathlib.Path.cwd() / ".evolverx" / "cache"
    )

    if args.cmd == "clean":
        num = clean_cache(
            base, getattr(args, "module", None), getattr(args, "func", None)
        )
        print(f"Removed {num} file(s)")
        return

    # default to show if no subcommand
    if args.cmd is None or args.cmd == "show":
        if getattr(args, "regen", False):
            regenerate_diff_artifacts(args.module, args.func, base)
        if args.show == "diff":
            diff = get_diff_text(args.module, args.func, base)
            if diff:
                print(diff)
            else:
                print("No diff available.")
        else:
            from .persist import get_diff_paths

            p = get_diff_paths(args.module, args.func, base)
            key = "diff_md" if args.show == "md" else "diff_html"
            print(p[key])
