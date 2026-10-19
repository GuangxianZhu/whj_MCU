# 交接说明（给新对话的 Claude 看）

新对话开头让 Claude 先读这个文件：仓库 `GuangxianZhu/whj_MCU`，`main` 分支，根目录 `HANDOFF.md`。

## 项目是什么

XL330 舵机通信的教学实验，面包板实物已经接好。信号链：

```
PC ──USB── KM1M7C（Nuvoton，3.3V IO）⇄ TXB0104（Adafruit 1875 模块，3.3V↔5V）⇄ SN74LVC2G241（5V，TX/RX 合成 DATA）⇄ XL330
```

- 用户是面包板初学者，搞嵌入式，用 Keil 写 MCU 程序，**不太会写程序**，希望改动越少越好。
- 交流用中文；用户喜欢选择题式的提问，不喜欢开放式打字。
- 用户习惯：做完就“推送 / 合并到 main”。用户说“另建文件”时就新建文件，不要覆盖旧的。

## 硬件要点（已在实物上确认）

- 面包板：28 列，只用下半块。每列槽下方 A–F 一组、槽上方 G–L 一组。V1 = 外部 5V（+ 靠里，− 靠外），V3 − = MCU 的 GND，V1 − 和 V3 − 用 P1 连通。
- 记号：“6下” = 第 6 列槽下方任一孔，“6上” = 槽上方；“红 4下，黑 V3 −” = 万用表红笔点 4下、黑笔点 V3 −。
- 241 转接板在第 6–9 列（G、F 行，1 脚在 6F）。TXB 模块在第 14–19 列：E 行 LV A1 A2 A3 A4 OE（LV 在 14E，OE 在 19E），G 行 HV B1 B2 B3 B4 GND（HV 在 14G）。
- 通道分配：A1/B1 = DIR，A2/B2 = RX，A3/B3 = TX；A4、OE 不接（模块上有 OE 10k 上拉和 LV/HV 0.1µF）；B4 接 GND。
- DATA 是第 4 列槽下方，舵机排针 2B = GND、3B = VDD、4B = DATA。
- 电阻：R1 = 10k（DATA 上拉，4G ↔ 4F）；R2 = 100k（RX 上拉，14K ↔ 16K）；R3 = 100k（DIR 下拉，6B ↔ 9B）。
  **踩过的坑**：R3 曾插成 10k，DIR = 1 时 B1 只有约 3.5V（TXB 输出内部串约 4kΩ，TI 要求外接上下拉 ≥ 50kΩ）。换成 100k 后实测 4.77V，正常。
- 接线编号（S1–S9、P1–P11、M1–M2、R1–R3、C2/C4/C5）和孔位全部在 `docs/breadboard/README.md` 的接线清单里；`python tools/check_wiring.py` 可核对接线清单和电路图是否一致。

## 现在的状态

- 用户的程序：只有一个 **手动切换 DIR（1/0）** 的口，PC 串口助手用 HEX **手动**发数据，没有循环发送。
- 已确认：DIR 那一路电平正常（换 R3 后 4.77V）。
- 还没收到过舵机应答。原因很可能是：舵机收到包约 0.5ms 后回答，**手动切 DIR 来不及**，必须由程序在发完后（等“发送完成” TC 标志）立刻把 DIR 切回 0。
- 下一步建议：按 `docs/breadboard/快速检查.md` 做——第 2 步拔掉 S7 做回环（DIR = 1 手动发 ping，应收回同样 10 字节），第 4 步 DIR = 1 发 LED 包看舵机 LED 亮不亮；要收 ping 应答，就在转发程序里加自动切 DIR（快速检查文末有示意代码）。
- 等用户提供：他现在能用的 KM1M7C UART / 转发代码（或 SDK 例程），以便写 `dxl_port_km1m7c.c`（实现 `firmware/dxl/dxl_port.h` 的 5 个函数 + `delay_ms` + `log_printf`），或直接在他的转发代码里加自动切 DIR。

## 仓库里有什么

| 路径 | 内容 |
|---|---|
| `docs/breadboard/README.md` | 电路图、面包板布局、逐根接线清单、模块内部图、物料、上电前检查（由 scratchpad 的 gen_readme.py 从页面数据生成） |
| `docs/breadboard/xl330_breadboard.html` | 交互版接线页面（同一份数据，`window.__XL330.STAGES`） |
| `docs/breadboard/快速检查.md/.html` | **推荐先用**：4 步 18 项，手动切 DIR，不用改程序 |
| `docs/breadboard/分级检查.md/.html` | 80 项：MCU → +TXB → +241 → +舵机，每项有目的，静态电平用跳线 |
| `docs/breadboard/通信全面检查.md/.html` | 86 项全面版 |
| `tools/check_wiring.py` | 接线网络核对（`--selftest` 自测） |
| `tools/*_check_data.py` | 三份检查表的数据源（生成 md 和页面 JSON） |
| `firmware/dxl/` | Protocol 2.0 驱动 `dxl.c/.h`、硬件接口 `dxl_port.h`、示例 `dxl_example.c`、测试程序 `dxl_bench.c`（'A' DIR=0、'B' DIR=1、'L' 回环、'S' 舵机） |
| `firmware/流程图.md` | 固件流程图（mermaid）：main()、dxl_txrx()、PC 转发 + 自动切 DIR |
| `firmware/test/host_test.c` | 电脑上跑的驱动测试：`cc -std=c99 -I../dxl ../dxl/dxl.c host_test.c && ./a.out` |

已发布的页面（用户私有链接）：接线页面 https://claude.ai/artifact/4Qn1ReW1PshwLSQkgHGXHQ ，快速检查 https://claude.ai/artifact/8BTS5Sn3S5jwhEpWnFRiHe ，分级检查 https://claude.ai/artifact/3tjyx3psWRoAS3vPzx615M ，全面检查 https://claude.ai/artifact/1fYqJRUWT76FcXKFh7SsPT 。

## 常用数据包（ID 1，57600 8N1，Protocol 2.0）

| 用途 | 字节 |
|---|---|
| ping | `FF FF FD 00 01 03 00 01 19 4E` |
| 广播 ping | `FF FF FD 00 FE 03 00 01 31 42` |
| LED 亮 / 灭 | `FF FF FD 00 01 06 00 03 41 00 01 CC E6` / `… 41 00 00 C9 66` |
| 广播 LED 亮 / 灭 | `FF FF FD 00 FE 06 00 03 41 00 01 3C 16` / `… 41 00 00 39 96` |
| ID 1 改为 2 / 3 | `FF FF FD 00 01 06 00 03 07 00 02 BD 63` / `… 07 00 03 B8 E3` |

正常 ping 应答：`FF FF FD 00 01 07 00 55 00 B0 04 xx CRC CRC`（14 字节，B0 04 = 型号 1200 / XL330-M288）。新的包用 `firmware/dxl/dxl.c` 里的 `dxl_crc16` 算 CRC，不要手算。

## 已讨论但没做的

- **多个 XL330**：电路不用改，舵机之间菊花链；先一个个改成不同 ID（地址 7）；电源按“个数 × 约 1.5A”选，舵机电源不要走面包板（触点约 1A），只留 DATA 和一根 GND；多个舵机同时动要加 Sync Write（驱动里还没有）。

## 提交方式

```sh
git checkout -b <branch>  # 改完
git -c user.name="GuangxianZhu" -c user.email="kenzayy267@gmail.com" commit -m "..."
git checkout main && git merge --no-ff <branch> && git push origin main <branch>
```
