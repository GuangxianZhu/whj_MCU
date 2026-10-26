# 明天让 ORCA 手动起来：一页纸步骤（官方命令版）

目标：**手能动、能演示握拳**。不追求完美，不碰固件。
全部用 **ORCA 官方的 orca_core**，按官方 README 的命令来，不用 Claude 写的 `Start-ORCA.bat`。

**已确认（2026-10-26）**：U2D2 在手边；舵机 ID 已设好 1–17；版本 **v2.0**（程序问硬件版本时输入 **2**）；舵机波特率 **57600**。

## 先记住三件事

1. **用 U2D2，不用 KM1M7。** 官方接法，程序自己能找到 U2D2（认它的 USB 厂商号 `0403`），波特率也自动扫。
2. **每条命令都在 `orca_core` 文件夹里运行**，开头都是 `uv run python`。
3. **急停**：命令行窗口按 **Ctrl+C**；还不行 → **拔 12V 电源**。电源插头放在手边。

## 接线

```
电脑 ──USB── U2D2 ──3P线── U2D2 Power Hub（PHB）── 舵机链（17 个）
                              └── 12V 适配器
```

- 舵机链分几条插到 PHB 不同的口，不要 17 个串成一条（一条线约 3 A 就到上限）。
- 适配器建议 8 A 以上（估算：17 个 × 300 mA 约 5 A，再留余量）。
- 上电顺序：先插 USB，再开 12V。

## 今晚 / 明早出发前（在要用的那台电脑上，约 15 分钟）

| 步骤 | 做什么 | 应该看到 |
|---|---|---|
| A | 装 Git for Windows（装过就跳过） | `git --version` 有输出 |
| B | 装 uv：PowerShell 里运行 `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`，关掉窗口重开 | `uv --version` 有输出 |
| C | 打开“命令提示符”（cmd），运行下面三行 | 最后一行装完没有红色报错 |
| D | U2D2 延迟改 1 ms（见下） | — |

```
git clone https://github.com/orcahand/orca_core
cd orca_core
uv sync
```

**D. U2D2 延迟改 1 ms**（ORCA 官方 Windows 说明）：设备管理器 → 端口（COM 和 LPT）→ USB Serial Port (COMx) → 属性 → Port Settings → Advanced → Latency Timer 改成 **1** → OK，拔插一次 U2D2。默认 16 ms，57600 下 17 个舵机一起读容易超时。找不到这个选项就先跳过，出现超时报错再回来改。

## 一个一个舵机检查（先接一个，再逐个加）

**规则：插拔舵机线之前先关 12V。**

orca_core 连接时只 ping config 里**第一个和最后一个 ID（1 和 17）**来确认“手在线”；其他没接的舵机会被当成“缺席”跳过，不报错（源码 `dynamixel_client.py` 的 `probe`、测试 `test_absent_motors.py`，确定）。所以：

1. **先只接 ID 1（手腕）** → 运行扫描（第 1 条命令）→ 应该只看到 ID 1 → 运行 `check_motor.py %CFG% --wrist`，手腕小幅来回转。
2. **ID 1 一直接着**，关电 → 再接一个（比如 ID 2）→ 开电 → 扫描，应该看到 ID 1、2 → `check_motor.py %CFG% --motor-id 2`。
3. 照这样一个一个加到 17。每加一个就扫描一次，新的那个出现了、能小幅转动，就打个勾。

| ID | 关节（右手） | 扫描看到 | 小幅转动 |
|---|---|---|---|
| 1 | 手腕 wrist | ☐ | ☐ |
| 2 | 食指 PIP | ☐ | ☐ |
| 3 | 食指 MCP | ☐ | ☐ |
| 4 | 食指侧摆 abd | ☐ | ☐ |
| 5 | 中指侧摆 abd | ☐ | ☐ |
| 6 | 无名指侧摆 abd | ☐ | ☐ |
| 7 | 无名指 MCP | ☐ | ☐ |
| 8 | 无名指 PIP | ☐ | ☐ |
| 9 | 中指 PIP | ☐ | ☐ |
| 10 | 中指 MCP | ☐ | ☐ |
| 11 | 小指 PIP | ☐ | ☐ |
| 12 | 小指 MCP | ☐ | ☐ |
| 13 | 小指侧摆 abd | ☐ | ☐ |
| 14 | 拇指侧摆 abd | ☐ | ☐ |
| 15 | 拇指 MCP | ☐ | ☐ |
| 16 | 拇指 DIP | ☐ | ☐ |
| 17 | 拇指 CMC | ☐ | ☐ |

（对照表来自官方右手 config 的 `joint_to_motor_map`。）

**为什么先接 ID 1**：只接一个 ID 5 这种“中间的”舵机时，程序 ping 不到 1 和 17，会认为没接手，`check_motor` 连不上。扫描（`--scan`）不受影响，任何 ID 都能扫到。

**线已经接在舵机上（腱绳装好）时**：`check_motor` 只在当前位置附近小幅来回转、有电流限制，是安全的。**不要用 Dynamixel Wizard 拖大角度**，腱绳会被拉断或拉松。

## 明天测试

每次打开新的 cmd 窗口，先运行这两行（以后的命令都用 `%CFG%` 代替那串很长的路径）：

```
cd orca_core
set CFG=orca_core\models\v2\orcahand-right\config.yaml
```

左手就把 `right` 换成 `left`。

然后按顺序，每步通过再做下一步：

| # | 命令（复制粘贴） | 做什么 | 应该看到 | 不对怎么办 |
|---|---|---|---|---|
| 1 | `uv run python scripts\configure_motor_chain.py %CFG% --scan` | **只读**，扫描总线上所有舵机（会扫好几种波特率，要等一会儿） | ID 1–17 共 17 个，波特率 57600，手指 XC330-T288-T、手腕 XC430 | 见下面“扫描结果怎么看” |
| 2 | `uv run python scripts\check_motor.py %CFG% --wrist` | 手腕小幅来回转。第一次会问硬件版本 → 输入 **2** | 手腕动一点点 | 不动 → 看电源、皮带 |
| 3 | `uv run python scripts\check_motor.py %CFG% --motor-id 2` | 食指 PIP（ID 2）小幅来回转 | 食指动一点点 | 记下现象 |
| 4 | `uv run python scripts\tension.py %CFG%` | 预紧：舵机把线拉直后顶住；用棘轮扳手**顺时针**拧每个舵机**上面**的卷线轮，听到咔哒，线**紧但不硬**就停；全部拧完按 Ctrl+C | 每根线都不松 | 别拧过头 |
| 5 | `uv run python scripts\calibrate.py %CFG%` | 自动标定：每个关节推到两头的限位（16 步，含手腕），几分钟 | 每个关节弯到底、伸到底 | 某个关节没动 → 记下名字，Ctrl+C 停 |
| 6 | 第 4、5 步**再做 1–2 次** | 新装的手第一次标定后线会松（官方说明就是这样） | 第二次以后不再出现松线 | — |
| 7 | `uv run python scripts\neutral.py %CFG%` | 回中立姿势 | 手自然张开 | — |
| 8 | `uv run python examples\main_demo.py %CFG%` | **演示：张开 → 握拳 → 捏**，3 次 | 给领导看这个 | — |

可以用一条命令代替第 4–6 步：`uv run python scripts\setup.py %CFG%`（官方装机向导：预紧 → 标定 3 轮，中间有开合测试，每步提示你按 Enter）。

其他可能用到的官方命令：

| 命令 | 做什么 |
|---|---|
| `uv run python scripts\manual_control.py %CFG%` | 电脑上的滑条，每个关节一个（标定以后） |
| `uv run python examples\main_demo.py %CFG% --demo abduction` | 演示：手指张开 / 并拢 |
| `uv run python scripts\calibrate.py %CFG% --joints wrist --force-wrist` | 只重新标定手腕 |
| `uv run python scripts\zero.py %CFG%` | 所有关节回 0° |

### 扫描结果怎么看（第 1 步）

| 看到 | 说明 | 做什么 |
|---|---|---|
| ID 1–17 全有 | 正常 | 继续第 2 步 |
| 少了几个 | 那几个线没插好或没电 | 查那几根 3P 线 |
| 一个都没有 | U2D2 没认到，或者 12V 没开 | 看 USB、电源开关；设备管理器里有没有 USB Serial Port |
| 有 ID 0 或 18 以上 | 有舵机 ID 不对 | 记下来，问 Claude（不要自己改） |

### 可选：让连接快一点

程序每次连接都会先试 1M、3M，再试其他波特率，最后才找到 57600。不影响使用，只是每次多等几秒。想省掉：用记事本打开 `orca_core\models\v2\orcahand-right\config.yaml`，在最上面加一行 `baudrate: 57600`，保存。

## 不要做的事

- 不要运行 `configure_motor_chain.py`（不带 `--scan`）：它是给新舵机设 ID 用的，我们的 ID 已经设好了。
- 不要加 `--baudrate`（会改舵机波特率）。
- 标定、预紧时手指附近不要放东西、不要用手挡。

## 给领导的一句话说明

ORCA 手用的是官方开源软件 orca_core（ETH Zurich，MIT 许可证），通过 U2D2 控制 17 个 Dynamixel 舵机（手指 XC330、手腕 XC430）；完成预紧和自动标定后，可以按关节角或预设手势控制。下一步计划把 U2D2 换成我们自己的 KM1M7C 板。
