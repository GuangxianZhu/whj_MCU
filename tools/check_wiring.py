#!/usr/bin/env python3
"""
check_wiring.py — 自动核对面包板接线清单和电路图是否一致。

做法：
  1. 从 docs/breadboard/xl330_breadboard.html 里读出接线清单（就是页面上那份，只有一个来源）。
  2. 按这块面包板的连通规则，把每个孔归到一个“导通节点”：
       - 同一列、槽下方 A–F 的 6 个孔相通；同一列、槽上方 G–L 的 6 个孔相通；
       - 每条电源轨（V1 +、V1 −、V3 +、V3 −）整条相通（上电前检查第 1 步要实测确认）。
  3. 放上芯片、排针，再按清单把导线和电阻电容接上，用并查集算出实际的网络。
  4. 和下面 REFERENCE（照电路图写的网络表）逐个网络比对：
       - 每个网络的所有引脚必须连在一起（不能漏接）；
       - 不同网络之间不能连在一起（不能短路）；
       - 电阻、电容两只脚必须跨在指定的两个网络上，电解电容还要分正负；
       - 不用的引脚（NC、B4）不能接到任何东西。
  5. 另外检查：同一个孔不能插两样东西；孔号存在；不往转接板边缘可能盖住的孔里插；
     不留只连了一头的“悬空”导线。

用法：
  python tools/check_wiring.py            核对，全部通过时退出码为 0
  python tools/check_wiring.py --selftest 故意改错几处，确认脚本能发现错误
只用 Python 标准库。
"""
import json
import re
import sys
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent / "docs" / "breadboard" / "xl330_breadboard.html"

# ---------------------------------------------------------------------------
# 面包板上的固定摆放（和清单里的 K1、K2、K3 对应）
# ---------------------------------------------------------------------------
TXB_COL, TXB_UPPER_ROW, TXB_LOWER_ROW = 14, "G", "E"   # 模块，第 14–19 列，针插 G 行和 E 行
G241_COL, G241_UPPER_ROW, G241_LOWER_ROW = 6, "G", "F"  # 第 6–9 列，针插 G 行和 F 行
HEADER = {"2B": "XL330.1", "3B": "XL330.2", "4B": "XL330.3"}  # 舵机 1 号 GND，2 号 VDD，3 号 DATA

# 转接板边缘可能盖住的孔：芯片所在列里，紧挨着针脚那一行（槽外侧）
def keepout_holes():
    k = set()
    for c in range(TXB_COL, TXB_COL + 6):
        k |= {f"{c}H", f"{c}D", f"{c}F"}       # F 在两排针中间，被模块盖住
    for c in range(G241_COL, G241_COL + 4):
        k |= {f"{c}H", f"{c}E"}
    return k

# ---------------------------------------------------------------------------
# 参考网络表（照电路图）
# 引脚写法：芯片.脚号，MCU.名字，EXT.+/-，XL330.脚号
# ---------------------------------------------------------------------------
REFERENCE = {
    "5V":      {"EXT.+", "TXB.VB", "241.8", "XL330.2"},
    "3V3":     {"MCU.3V3", "TXB.VA"},
    "GND":     {"EXT.-", "MCU.GND", "TXB.GND", "TXB.B4", "241.4", "XL330.1"},
    "DIR_3V3": {"MCU.DIR", "TXB.A1"},
    "RX_3V3":  {"MCU.RX", "TXB.A2"},
    "TX_3V3":  {"MCU.TX", "TXB.A3"},
    "DIR_5V":  {"TXB.B1", "241.7", "241.1"},
    "RX_5V":   {"TXB.B2", "241.6"},
    "TX_5V":   {"TXB.B3", "241.5"},
    "DATA":    {"241.2", "241.3", "XL330.3"},
}
UNUSED = {"TXB.A4", "TXB.OE"}                  # A4 不用；OE 由模块内部 10k 上拉到 LV，外面不接
PARTS = {                                       # 两只脚跨在哪两个网络上
    "R1": ("DATA", "5V"),
    "R2": ("RX_5V", "5V"),
    "R3": ("DIR_5V", "GND"),
    "C2": ("5V", "GND"),
    "C5": ("5V", "GND"),
    "C4": ("5V", "GND"),                        # 电解电容：第一只脚是 +
}
POLARIZED = {"C4"}

RAILS = {"V1P", "V1N", "V3P", "V3N"}
ROWS = "ABCDEFGHIJKL"


# ---------------------------------------------------------------------------
def load_stages(path=PAGE):
    """从页面里取出 STAGES 数组，转成 Python 数据。"""
    s = path.read_text(encoding="utf-8")
    m = re.search(r"const STAGES=(\[.*?\n  \]);", s, re.S)
    if not m:
        raise SystemExit("页面里找不到接线清单（const STAGES=...）")
    js = m.group(1)
    js = re.sub(r",\s*\{(?:b|ctrl):[^{}]*\}\s*\]", "]", js)  # 去掉只给画图用的选项 {b:0} / {ctrl:[...]}
    js = re.sub(r"([{,]\s*)(t|d|items):", r'\1"\2":', js)  # 给键名加引号
    js = js.replace("'", '"')
    return json.loads(js)


def items_of(stages):
    for st in stages:
        for it in st["items"]:
            yield it


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def node_of(pos, errors):
    """把位置换成导通节点。返回 (节点, 孔号或 None)。"""
    if ":" in pos:
        k, v = pos.split(":", 1)
        if k in RAILS:
            if v not in ROWS:
                errors.append(f"电源轨孔号不存在：{pos}")
            return k, pos
        if k == "MCU":
            return f"MCU.{v}", None
        if k == "EXT":
            return f"EXT.{v}", None
        errors.append(f"认不出的位置：{pos}")
        return pos, None
    m = re.fullmatch(r"(\d+)([A-L])", pos)
    if not m or not 1 <= int(m.group(1)) <= 28:
        errors.append(f"孔号不存在：{pos}")
        return pos, pos
    c, r = int(m.group(1)), m.group(2)
    return f"col{c}{'下' if r in 'ABCDEF' else '上'}", pos


def chip_pins():
    """芯片和排针的每只脚插在哪个孔。"""
    pins = {}
    lower = ["VA", "A1", "A2", "A3", "A4", "OE"]   # TXB0104 模块：两排从左到右
    upper = ["VB", "B1", "B2", "B3", "B4", "GND"]
    for i in range(6):
        pins[f"TXB.{lower[i]}"] = f"{TXB_COL + i}{TXB_LOWER_ROW}"
        pins[f"TXB.{upper[i]}"] = f"{TXB_COL + i}{TXB_UPPER_ROW}"
    for i in range(4):                       # 74LVC2G241：1–4 下排，5–8 上排
        pins[f"241.{1 + i}"] = f"{G241_COL + i}{G241_LOWER_ROW}"
        pins[f"241.{8 - i}"] = f"{G241_COL + i}{G241_UPPER_ROW}"
    for hole, name in HEADER.items():
        pins[name] = hole
    return pins


def check(stages, verbose=True):
    errors, warnings = [], []
    dsu = DSU()
    used = {}                                # 孔 -> 谁占用
    terminals = {}                           # 引脚 -> 节点

    def occupy(hole, who):
        if hole is None:
            return
        if hole in used:
            errors.append(f"孔 {hole} 被插了两次：{used[hole]} 和 {who}")
        else:
            used[hole] = who

    for pin, hole in chip_pins().items():
        n, h = node_of(hole, errors)
        occupy(h, pin)
        terminals[pin] = n
        dsu.find(n)
    for t in ("MCU.3V3", "MCU.GND", "MCU.DIR", "MCU.RX", "MCU.TX", "EXT.+", "EXT.-"):
        terminals[t] = t
        dsu.find(t)

    # K 步骤里写的列号要和这里的摆放一致
    ktext = {it[0]: it[2] + " " + it[5] for it in items_of(stages) if it[1] == "k"}
    expect = {"K1": f"第 {TXB_COL}–{TXB_COL + 5} 列", "K2": f"第 {G241_COL}–{G241_COL + 3} 列",
              "K3": "2B、3B、4B"}
    for k, frag in expect.items():
        if frag not in ktext.get(k, ""):
            errors.append(f"{k} 的说明和脚本里的摆放对不上（应包含“{frag}”）")

    keep = keepout_holes()
    part_nodes = {}
    wire_ends = []
    seen_ids = set()
    for it in items_of(stages):
        iid, kind, a, b = it[0], it[1], it[2], it[3]
        if iid in seen_ids:
            errors.append(f"编号重复：{iid}")
        seen_ids.add(iid)
        if kind == "k":
            continue
        na, ha = node_of(a, errors)
        nb, hb = node_of(b, errors)
        for h in (ha, hb):
            occupy(h, iid)
            if h in keep:
                warnings.append(f"{iid} 用到 {h}，这个孔紧挨着转接板，可能被盖住")
        if kind == "w":
            dsu.union(na, nb)
            wire_ends.append((iid, na, nb))
        else:
            part_nodes[iid] = (na, nb)

    # 每个引脚所在的网络
    net_of = {p: dsu.find(n) for p, n in terminals.items()}

    # 1) 每个参考网络必须连成一个；2) 不同网络不能相连
    root_owner = {}
    for name, pins in REFERENCE.items():
        roots = {net_of[p] for p in pins}
        if len(roots) > 1:
            groups = {}
            for p in sorted(pins):
                groups.setdefault(net_of[p], []).append(p)
            errors.append(f"{name} 没有连成一个网络，被分成了 {len(roots)} 段：" +
                          " | ".join("、".join(v) for v in groups.values()))
        for r in roots:
            if r in root_owner and root_owner[r] != name:
                errors.append(f"短路：{root_owner[r]} 和 {name} 被接在了一起")
            root_owner.setdefault(r, name)
    for p in sorted(UNUSED):
        r = net_of[p]
        others = [q for q, rr in net_of.items() if rr == r and q != p]
        if others or r in root_owner:
            errors.append(f"{p} 应该不接，却连到了 {root_owner.get(r) or '、'.join(others)}")

    def ref_name(node):
        return root_owner.get(dsu.find(node))

    # 3) 电阻电容跨在正确的两个网络上
    for pid, want in PARTS.items():
        if pid not in part_nodes:
            errors.append(f"清单里没有 {pid}")
            continue
        got = tuple(ref_name(n) or "（没接到任何网络）" for n in part_nodes[pid])
        ok = got == want if pid in POLARIZED else sorted(map(str, got)) == sorted(want)
        if not ok:
            errors.append(f"{pid} 应该接在 {want[0]} 和 {want[1]} 之间，实际是 {got[0]} 和 {got[1]}")
    for pid in part_nodes:
        if pid not in PARTS:
            warnings.append(f"{pid} 不在参考网络表里，没有核对")

    # 4) 导线两头都要落在有用的网络上
    for iid, na, nb in wire_ends:
        if ref_name(na) is None:
            errors.append(f"{iid} 的一头悬空（{na} 上没有任何引脚）")

    n_stages = len(stages)
    if n_stages < 7:
        errors.append(f"只读到 {n_stages} 组接线，页面里应该有 7 组，可能没读全")

    if verbose:
        n_items = sum(1 for it in items_of(stages) if it[1] != "k")
        print(f"核对了 {n_items} 根线和元件、{len(REFERENCE)} 个网络、{len(PARTS)} 个电阻电容。")
        for w in warnings:
            print("提醒：" + w)
        if errors:
            for e in errors:
                print("错误：" + e)
        else:
            print("全部通过：接线清单和电路图一致，没有漏接、短路或重复插孔。")
    return errors, warnings


def selftest():
    """故意改错，确认每种错误都能被发现。"""
    import copy
    base = load_stages()

    def mutate(fn):
        st = copy.deepcopy(base)
        for it in items_of(st):
            if fn(it):
                break
        return st

    cases = [
        ("TX 线接到 RX 的列（交叉接错）", lambda it: it[0] == "S3" and not it.__setitem__(3, "16C")),
        ("漏掉 P1（两边的地没接通）", lambda it: it[0] == "P1" and not it.__setitem__(3, "V1N:K")),
        ("R1 插错一列（一头悬空）", lambda it: it[0] == "R1" and not it.__setitem__(2, "2G")),
        ("电解电容 C4 正负接反", lambda it: it[0] == "C4" and not (it.__setitem__(2, "V1N:B"), it.__setitem__(3, "V1P:B"))),
        ("两样东西插进同一个孔", lambda it: it[0] == "P12" and not it.__setitem__(2, "16B")),
        ("5V 和 3.3V 短路（3.3V 插到了槽上方）", lambda it: it[0] == "M1" and not it.__setitem__(3, "14J")),
        ("B4 的接地线插到了 A4 那一列", lambda it: it[0] == "P12" and not it.__setitem__(2, "18B")),
        ("OE 被误接到 GND", lambda it: it[0] == "P12" and not it.__setitem__(2, "19B")),
    ]
    failed = 0
    for name, fn in cases:
        errs, _ = check(mutate(fn), verbose=False)
        mark = "能发现" if errs else "没发现！"
        failed += not errs
        print(f"[{mark}] {name}" + (f"：{errs[0]}" if errs else ""))
    errs, _ = check(base, verbose=False)
    print(f"[{'通过' if not errs else '失败'}] 原始清单" + ("" if not errs else f"：{errs}"))
    return failed == 0 and not errs


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    errs, _ = check(load_stages())
    sys.exit(1 if errs else 0)
