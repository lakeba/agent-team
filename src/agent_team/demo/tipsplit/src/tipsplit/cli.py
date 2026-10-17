import argparse


def split(total: float, people: int, tip: float = 0.0) -> float:
    """Each person's share of the bill, with the tip, in currency units."""
    return round(total * (1 + tip / 100) / people, 2)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="tipsplit")
    p.add_argument("total", type=float)
    p.add_argument("--people", type=int, default=1)
    p.add_argument("--tip", type=float, default=0.0)
    a = p.parse_args(argv)
    print(f"{split(a.total, a.people, a.tip):.2f} each")


if __name__ == "__main__":
    main()
