"""Generate docs/一根手指.md with every packet built by tools/dxl_packet.py (no hand-typed CRC)."""
import sys
REPO = sys.argv[1]
sys.path.insert(0, REPO + "/tools")
import dxl_packet as d

R, M, T = 0, 1, 2            # root MCP, middle PIP, tip DIP
J = [(R, "根部"), (M, "中间"), (T, "指尖")]
STRAIGHT, FULL = 2048, {R: 3072, M: 3072, T: 2731}
HALF = {R: 2560, M: 2560, T: 2389}

def p(*a):
    return "`" + d.hexs(d.build([str(x) for x in a])) + "`"

def ack(i):
    b = bytes([0xFF, 0xFF, 0xFD, 0x00, i, 0x04, 0x00, 0x55, 0x00])
    c = d.crc16(b)
    return "`" + d.hexs(b + bytes([c & 0xFF, c >> 8])) + "`"

def sg(r, m, t):
    return p("sync-goal", f"{R}:{r}", f"{M}:{m}", f"{T}:{t}")

def per(fmt, *args_fn):
    return "、".join(f"ID {i} {p(*fn(i))}" for i, _ in J for fn in args_fn)

def each(cmd):  # list per ID, cmd(i) -> args
    return "、".join(f"ID {i} {p(*cmd(i))}" for i, _ in J)

open_ = sg(STRAIGHT, STRAIGHT, STRAIGHT)
half = sg(HALF[R], HALF[M], HALF[T])
full = sg(FULL[R], FULL[M], FULL[T])
hook = sg(STRAIGHT, FULL[M], FULL[T])
b1 = sg(FULL[R], STRAIGHT, STRAIGHT)
b2 = sg(FULL[R], FULL[M], STRAIGHT)
syncpos = p("sync-pos", R, M, T)

out = []
w = out.append
w(f"""# 一根手指：3 个 XC330 弯曲成“抓”的样子

2026-10-23。现在先在桌上模拟（3 个舵机摆在桌上，看舵盘转），手指结构以后再装。控制方式：串口助手发 HEX（经 M7C 面包板转发，和以前一样）。
本页所有数据包都由 `tools/dxl_packet.py` 生成（生成脚本见文末），不是手算的。

## 一句话总结

三个关节各给一个目标角度，用**一个 Sync Write 包**同时发出去；再把三个舵机设成**“时间型运动曲线”**，让它们转的角度不同也**同时开始、同时到达**。看起来就是一根手指平滑地弯起来。

## 分工

用户的三个手指舵机 ID 是 **0、1、2**（ID 0 是合法的，范围 0–252）。这里按“从根部到指尖”的顺序对应；如果实际顺序不同，告诉 Claude 重新生成。

| ID | 关节 | 舵机 | 伸直 | 握紧（弯曲量） |
| --- | --- | --- | --- | --- |
| {R} | 根部 MCP（掌指关节） | XC330 | 2048 | {FULL[R]}（+90°） |
| {M} | 中间 PIP（近端指间关节） | XC330 | 2048 | {FULL[M]}（+90°） |
| {T} | 指尖 DIP（远端指间关节） | XC330 | 2048 | {FULL[T]}（+60°） |
| 3 | 手腕（以后用） | XC430-T240BB | — | — |

- 约定：**数值变大 = 弯曲**，2048 = 伸直。一圈 4096，所以 90° = 1024，60° ≈ 683。
- 指尖只弯 60°：人的手指指尖关节弯曲大约是中间关节的 2/3（这是做假手和机械手时常用的经验比例，不是严格规律）。手指装好以后可以按实际结构改。
- 指尖为什么不也弯 90°：真手指握拳时指尖关节弯得最少，三个一样弯会像“钩子”而不像握东西。
- 手腕的 XC430 目前是 ID 3，和 0/1/2 不冲突，**不用改**。以后想改成 10 也可以（只接它一个，关扭矩后发 {p("setid", 3, 10)}）。

---

## 原理：为什么要“时间型运动曲线”

**先猜一下**：出厂设置下（速度型曲线，三个舵机速度一样），发“握紧”这个包：根部转 90°、指尖转 60°。哪个先到？
A. 根部先到　B. 指尖先到　C. 同时到

答案是 **B**。速度一样时，转得少的先到。指尖早早弯完停住，根部还在转，动作看起来一节一节的，很机械。

把三个舵机的 Drive Mode（地址 10）bit 2 设成 1，就是**时间型曲线**：Profile Velocity（地址 112）不再表示速度，而是“**用多少毫秒到达**”；Profile Acceleration（地址 108）是加速、减速各用多少毫秒。三个都设 1000 ms，那么不管各自转多少度，都在 1 秒内同时到达，中间是先加速再减速的平滑曲线。

依据和可信度：
- Drive Mode bit 2 = 时间型曲线、地址 108 的单位有 “1 msec”：出自 XC330-T288 e-Manual 控制表（公认结论）。
- “按指定时间完成动作、与距离无关”：出自 ROBOTIS 官方文章（公认结论）。
- Profile Velocity 在时间型下的单位是 ms、加速时间要小于总时间的一半：按 ROBOTIS X 系列文档的通常说明，但这个舵机的页面我没能读到这一段（较可信，未实测）。**第 5 步就是用眼睛验证它。**

条件：Drive Mode 在 EEPROM 里，**Torque 关着才能写**；写一次断电也不丢。Profile Velocity / Acceleration 在 RAM 里，**每次上电都要重新发**。

---

## 第 1 步：三个 XC330 一起接上

1. PHB 开关关。三个 XC330 接到 PHB（每个直接插 PHB，或串起来都可以；三个 XC330 最坏约 2.6A，桌上空转远小于这个）。XC430 这次可以不接。
2. 三个舵机摆在桌上，**舵盘上贴一条胶带当“指节”**，方便看角度。舵机身体用胶带或夹子固定在桌上，舵盘周围留出空间。
3. 上电：M7C 的 USB → 外部 5V → PHB 开关。
4. 广播 ping：{p("ping", "all")} → 三个应答共 42 字节，第 5 个字节分别是 `00`、`01`、`02`。
5. 给舵机贴标签：ID {R} “根部”、ID {M} “中间”、ID {T} “指尖”。分不清哪个是哪个时，单独亮 LED：""")
for i, n in J:
    w(f"    - ID {i} LED 亮 {p('led', i, 'on')}，灭 {p('led', i, 'off')}")
w("")
w(f"""## 第 2 步：设成时间型曲线（只做一次，Torque 关着）

每条的正常应答：""" + "，".join(f"ID {i} {ack(i)}" for i, _ in J) + "。\n")
w("| # | 做什么 | 发送 |\n| --- | --- | --- |")
k = 1
for i, _ in J:
    w(f"| 2-{k} | ID {i} 关扭矩 | {p('torque', i, 'off')} |"); k += 1
for i, _ in J:
    w(f"| 2-{k} | ID {i} Drive Mode = 4（时间型） | {p('write', i, 10, 1, 4)} |"); k += 1
w(f"| 2-{k} | 确认（读地址 10） | " + "、".join(f"ID {i} {p('read', i, 10, 1)}" for i, _ in J) + " → 应答参数都是 `04` |")
w("")
w("## 第 3 步：每次上电后先发这 9 条（RAM，断电会丢）\n")
w("| # | 做什么 | 发送 |\n| --- | --- | --- |")
k = 1
for i, n in J:
    w(f"| 3-{k} | ID {i}（{n}）加减速 300 ms | {p('write', i, 108, 4, 300)} |"); k += 1
    w(f"| 3-{k} | ID {i}（{n}）总时间 1000 ms | {p('write', i, 112, 4, 1000)} |"); k += 1
for i, n in J:
    w(f"| 3-{k} | ID {i} Torque 开 | {p('torque', i, 'on')} |"); k += 1
w("")
w("想快一点（0.5 秒、加减速 150 ms）就把 3-1～3-6 换成：")
for i, _ in J:
    w(f"- ID {i}：{p('write', i, 108, 4, 150)}、{p('write', i, 112, 4, 500)}")
w("")
w(f"""## 第 4 步：认方向（在胶带上画箭头）

数值变大时，舵盘从正面看是**逆时针**转（XC330 出厂是 Normal 模式：CCW 为正）。在桌上模拟时，就把“逆时针”当成“弯曲”。每个舵机单独试一下，先回 2048 再到 2304（+22.5°），1 秒内平滑转到：

| 关节 | → 2048 | → 2304 |
| --- | --- | --- |""")
for i, n in J:
    w(f"| ID {i} {n} | {p('goal', i, 2048)} | {p('goal', i, 2304)} |")
w(f"""
以后装进真手指时，如果某个舵机装反了（数值变大时手指往外翻），**不用改任何手势包**：Torque 关着时把它的 Drive Mode 改成 **5**（时间型 + 反向，bit 0 = 1）：""" + each(lambda i: ("write", i, 10, 1, 5)) + """。反向后读回的位置也跟着反，所以“变大 = 弯曲”对每个关节都成立。注意：反向后伸直位置对应的数值可能会变，装好实物时要重新确认伸直值。

## 第 5 步：手势（每个只发一个包）

全部是 Sync Write，**没有应答是正常的**。每个手势 1 秒内三个关节同时到达。

| 手势 | 根部 / 中间 / 指尖 | 发送 |
| --- | --- | --- |""")
w(f"| **张开**（伸直） | 2048 / 2048 / 2048 | {open_} |")
w(f"| **半握** | {HALF[R]} / {HALF[M]} / {HALF[T]}（45° / 45° / 30°） | {half} |")
w(f"| **握紧** | {FULL[R]} / {FULL[M]} / {FULL[T]}（90° / 90° / 60°） | {full} |")
w(f"| **钩**（像提袋子） | 2048 / {FULL[M]} / {FULL[T]}（根部直，前两节弯） | {hook} |")
w(f"""
**验证时间型曲线**：先发“张开”，等 2 秒，再发“握紧”。三条胶带应该**同时开始、同时停**，指尖转得少所以转得慢。如果指尖明显先停：
1. 读三个的 Drive Mode（第 2 步最后一行），确认是 `04`；
2. 确认第 3 步 3-1～3-6 都发了、都有应答；
3. 还不行，改用下面的“备用做法”，并告诉 Claude。

**备用做法（速度型，按比例设速度）**：Torque 关 → Drive Mode 写回 0（""" + each(lambda i: ("write", i, 10, 1, 0)) + "）→ 加速度 0（" + each(lambda i: ("write", i, 108, 4, 0)) + "）→ 速度按转角比例：根部、中间 30，指尖 20（= 30 × 60/90）（" + "、".join(f"ID {i} {p('write', i, 112, 4, v)}" for i, v in ((R, 30), (M, 30), (T, 20))) + """）→ Torque 开。这样只在“张开 ↔ 握紧”之间同时到达；换别的手势比例就不对了，所以时间型更好。

## 第 6 步：两种“抓”的动作

**A. 一起弯（最自然，推荐）**：在串口助手里循环发：握紧 → 等 1.5 秒 → 张开 → 等 1.5 秒。很多串口助手有“多条发送 / 定时循环”功能（比如 SSCOM 的“多字符串”，每条可以设延时），把两条填进去，间隔 1500 ms。

**B. 从根部卷到指尖（像把东西卷进手心）**：依次发，每条间隔约 0.5 秒（不用等前一个动作完全做完，时间重叠会更顺）：

| 顺序 | 根部 / 中间 / 指尖 | 发送 |
| --- | --- | --- |""")
w(f"| B1 | {FULL[R]} / 2048 / 2048 | {b1} |")
w(f"| B2 | {FULL[R]} / {FULL[M]} / 2048 | {b2} |")
w(f"| B3 | {FULL[R]} / {FULL[M]} / {FULL[T]} | 同“握紧” |")
w("| 松开 | 2048 / 2048 / 2048 | 同“张开” |")
w(f"""
为什么 B 能“提前发”：每个舵机收到新目标时，会从**当前位置**重新规划一条 1 秒的曲线，所以前一个动作没做完就发下一个也不会出错，只是动作连在一起了。

**读位置**（看到底转到哪）：{syncpos} → 三个应答各 15 字节，按 ID {R}、{M}、{T} 顺序；用 `python tools/dxl_packet.py parse "…"` 解读。

## 第 7 步：结束

张开 → 三个 Torque 关（""" + each(lambda i: ("torque", i, "off")) + """）→ PHB 开关 → 外部 5V → USB。

---

## 以后装到真手指时（现在不用做）

1. **先设位置限制**（EEPROM，Torque 关着写），让舵机不会把手指掰过头。按上面的伸直/握紧值：
    - 最小值（地址 52）= 2048：""" + each(lambda i: ("write", i, 52, 4, 2048)) + """
    - 最大值（地址 48）：""" + "、".join(f"ID {i} = {FULL[i]} {p('write', i, 48, 4, FULL[i])}" for i, _ in J) + """
    - 装好以后伸直位置不一定正好是 2048，要先量实际的伸直值再改这些数。
2. **真的抓东西时用“电流限制的位置控制”**（Operating Mode 地址 11 = 5，XC330 支持）。它会限制每个关节用的力（Goal Current，地址 102，单位约 1 mA），手指碰到东西就停在那里、只用设定的力夹住，不会一直硬顶到发热或报过载。这是机械手抓取的主流做法。注意：切换模式会把 Profile 设回 0、重置部分 PID，要重新发第 3 步。

## 风险

| 风险 | 对策 |
| --- | --- |
| 写 Drive Mode 时 Torque 开着 | 写不进去；先关扭矩（2-1～2-3） |
| 忘了第 3 步（断电后 Profile 变回 0） | Profile Velocity = 0 表示不做曲线、按最快速度转（X 系列文档的说明），会很猛；每次上电先发第 3 步 |
| 舵机在桌上被自己带着转 | 用胶带或夹子把舵机身体固定在桌上，只让舵盘转 |
| 拿以前的包（ID 1/2/3）来用 | 以前文档里的包是 ID 1、2、3；手指现在是 ID 0、1、2，用本页的包 |
| `dxl_example2.c` / `dxl_example3.c` | 那是旧的 ID 分配（1/2、1/2/3）的示例，跑手指要先把 `IDS` 改成 {{0, 1, 2}} |

## 来源

- [XC330-T288 e-Manual](https://emanual.robotis.com/docs/en/dxl/x/xc330-t288/)（Drive Mode 位定义、Profile 地址和单位、Operating Mode 5、Current Limit / Goal Current、位置限制、ID 范围 0–252）
- [DYNAMIXEL drive modes and their various capabilities（ROBOTIS）](https://robotis.us/dynamixel-drive-modes-and-their-various-capabilities-)（时间型曲线：按指定时间完成动作，与距离无关）
- [DYNAMIXEL Protocol 2.0](https://emanual.robotis.com/docs/en/dxl/protocol2/)（Sync Write、Sync Read）

生成脚本：`tools/gen_finger_doc.py`（改 ID 或角度时改脚本开头的几个数，再运行 `python tools/gen_finger_doc.py .`）。
""")
open(REPO + "/docs/一根手指.md", "w", encoding="utf-8").write("\n".join(out))
print("written")
