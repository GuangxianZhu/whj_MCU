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

- **一个 XL330 已经驱动成功**（用户 2026-10-20 告知）。
- 用户原来的程序：一个手动切换 DIR（1/0）的口，PC 串口助手用 HEX 手动发数据。
- 已写好转发固件 `firmware/bridge/`（按包转发 PC 的数据、自动切 DIR、应答原样回 PC），用户要把 `bridge_main_template.c` 里的 TODO 换成 KM1M7C 的 SDK 调用（两个 UART、DIR GPIO、SysTick）。用户提供 SDK 例程或现有 UART 代码时，可以帮他填。
- 下一步：接第二个舵机，按 `docs/两个舵机.md`：先单独把第二个改成 ID 2，再串起来做 T1–T8 测试；两个同时用力时电源要 3 A 以上，舵机电源最好不走面包板。
- 以后：根据传感器数据更新指令包（设计在 `firmware/应用通信流程.md` 第 6 节，用 `bridge_submit()`）。

## 仓库里有什么

| 路径 | 内容 |
|---|---|
| `docs/breadboard/README.md` | 电路图、面包板布局、逐根接线清单、模块内部图、物料、上电前检查（由 scratchpad 的 gen_readme.py 从页面数据生成） |
| `docs/breadboard/xl330_breadboard.html` | 交互版接线页面（同一份数据，`window.__XL330.STAGES`） |
| `docs/breadboard/快速检查.md/.html` | **推荐先用**：4 步 18 项，手动切 DIR，不用改程序 |
| `docs/breadboard/分级检查.md/.html` | 80 项：MCU → +TXB → +241 → +舵机，每项有目的，静态电平用跳线 |
| `docs/breadboard/通信全面检查.md/.html` | 86 项全面版 |
| `docs/exploded/xl330_exploded.html` | three.js 3D 爆炸图（单文件，CDN 加载 three@0.169.0）：整套接线 + 舵机内部（示意）+ TX/RX 信号流动画；根目录 `Start-Exploded-View.bat` 先 git pull main 再打开。接线数据 `WIRES` 抄自 `xl330_breadboard.html`，改接线时两边一起改 |
| `tools/check_wiring.py` | 接线网络核对（`--selftest` 自测） |
| `tools/*_check_data.py` | 三份检查表的数据源（生成 md 和页面 JSON） |
| `firmware/dxl/` | Protocol 2.0 驱动 `dxl.c/.h`、硬件接口 `dxl_port.h`、示例 `dxl_example.c`、测试程序 `dxl_bench.c`（'A' DIR=0、'B' DIR=1、'L' 回环、'S' 舵机） |
| `firmware/应用通信流程.md` | 用户要照着写的转发固件设计：按包转发 PC 的数据、请求队列、总线事务，以后加传感器作为第二个指令来源 |
| `firmware/流程图.md` | 固件流程图（mermaid）：main()、dxl_txrx()、PC 转发 + 自动切 DIR |
| `firmware/bridge/` | 转发固件：`bridge.c/.h`、`bridge_port.h`（PC 写和毫秒时钟两个函数）、`bridge_main_template.c`（填 TODO 的模板）；测试 `firmware/test/bridge_test.c` |
| `firmware/dxl/dxl_example2.c` | 两个舵机的示例（Sync Write / Sync Read） |
| `docs/两个舵机.md` | 接第二个舵机的调研、电源、改 ID 步骤、测试 T1–T8 |
| `tools/dxl_packet.py` | 生成任意包的 HEX（`ping 2`、`setid 1 2`、`sync-goal 1:1024 2:3072` …）和解读应答（`parse "…"`）；`selftest` 对照 e-Manual 例子 |
| `firmware/test/host_test.c` | 电脑上跑的驱动测试：`cc -std=c99 -I../dxl ../dxl/dxl.c host_test.c && ./a.out` |

已发布的页面（用户私有链接）：接线页面 https://claude.ai/artifact/4Qn1ReW1PshwLSQkgHGXHQ ，快速检查 https://claude.ai/artifact/8BTS5Sn3S5jwhEpWnFRiHe ，分级检查 https://claude.ai/artifact/3tjyx3psWRoAS3vPzx615M ，全面检查 https://claude.ai/artifact/1fYqJRUWT76FcXKFh7SsPT ，固件流程图 https://claude.ai/artifact/JjVaevA95feM5GqgyKTArE ，应用通信流程 https://claude.ai/artifact/REfWcoEBPBHtqpvm7pciKv 。

## 常用数据包（ID 1，57600 8N1，Protocol 2.0）

| 用途 | 字节 |
|---|---|
| ping | `FF FF FD 00 01 03 00 01 19 4E` |
| 广播 ping | `FF FF FD 00 FE 03 00 01 31 42` |
| LED 亮 / 灭 | `FF FF FD 00 01 06 00 03 41 00 01 CC E6` / `… 41 00 00 C9 66` |
| 广播 LED 亮 / 灭 | `FF FF FD 00 FE 06 00 03 41 00 01 3C 16` / `… 41 00 00 39 96` |
| ID 1 改为 2 / 3 | `FF FF FD 00 01 06 00 03 07 00 02 BD 63` / `… 07 00 03 B8 E3` |
| ping 2 | `FF FF FD 00 02 03 00 01 19 72` |
| Sync Write：ID 1 → 1024，ID 2 → 3072 | `FF FF FD 00 FE 11 00 83 74 00 04 00 01 00 04 00 00 02 00 0C 00 00 13 0C` |
| Sync Read 两个当前位置 | `FF FF FD 00 FE 09 00 82 84 00 04 00 01 02 CE FA` |

正常 ping 应答：`FF FF FD 00 01 07 00 55 00 B0 04 xx CRC CRC`（14 字节，B0 04 = 型号 1200 / XL330-M288）。新的包用 `python tools/dxl_packet.py …` 生成（和固件 `dxl_crc16` 结果一致），不要手算。

## 已做但还没在实物上验证 / 还没做的

- 两个舵机的软件和计划已经做好（`docs/两个舵机.md`、驱动的 Sync Write/Read），**还没在实物上测**。
- 转发固件 `firmware/bridge/` 只在电脑上测过，**还没在 KM1M7C 上跑**；模板里的 TODO 要用 SDK 填。
- 根据传感器数据控制：只有设计（`firmware/应用通信流程.md` 第 6 节），还没写代码。

## 提交方式

```sh
git checkout -b <branch>  # 改完
git -c user.name="GuangxianZhu" -c user.email="kenzayy267@gmail.com" commit -m "..."
git checkout main && git merge --no-ff <branch> && git push origin main <branch>
```
