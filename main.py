#!/usr/bin/env python3
"""Command line entrypoint for the China non-tech jobs radar."""

import argparse

from radar.pipeline import build_outputs, fetch_and_build, validate_data


def main() -> None:
    parser = argparse.ArgumentParser(description="中国科技公司非技术岗信息雷达")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="从官方招聘源抓取并生成所有产物")
    fetch_parser.add_argument("--max-pages", type=int, default=50, help="每个数据源最多抓取页数")

    subparsers.add_parser("build", help="从 data/jobs.json 重新生成 README、CSV 和静态站点数据")
    subparsers.add_parser("validate", help="校验岗位数据 schema、分类和唯一性")

    args = parser.parse_args()
    if args.command == "fetch":
        fetch_and_build(max_pages=args.max_pages)
    elif args.command == "build":
        build_outputs()
    else:
        validate_data()


if __name__ == "__main__":
    main()
