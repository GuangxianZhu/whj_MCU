# 明天让 ORCA 手动起来：一页纸步骤（官方命令版）

目标：**手能动、能演示握拳**。不追求完美，不碰固件。
全部用 **ORCA 官方的 orca_core**，按官方 README 的命令来，不用 Claude 写的 `Start-ORCA.bat`。

**已确认（2026-10-26）**：**左手**；U2D2 在手边；舵机 ID 已设好 1–17；版本 **v2.0**（程序问硬件版本时输入 **2**）；舵机波特率 **57600**。

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

## 一根一根装腱绳、一个一个检查（2026-10-26 用户选的做法）

思路：**装好一个舵机的腱绳 → 只给这个舵机预紧、标定 → 用滑条确认能动 → 再装下一个**。哪根线有问题马上就知道。

### 两条规则（都来自读 orca_core 源码，确定）

1. **通信线只接“ID 1（手腕）+ 正在装的这一个”**，其他舵机的 3P 线先拔掉。
   - 程序连接时只 ping ID 1 和 17 来确认手在线，所以 ID 1 要一直接着。
   - 预紧（`tension.py`）会让**所有接着的手指舵机**正反各转一段（每个方向最多 20 秒）直到线拉紧；没接的舵机会被跳过。所以只接这一个，没装线的卷线轮就不会白转、线不会缠。
2. **标定只标这一个关节**：`calibrate.py %CFG% --joints 关节名`，程序只驱动这个关节（同一步里的其他关节不动）。标好的结果存在 `calibration.yaml`，以后标别的关节不会覆盖它。

**插拔通信线前先关 12V。**

### 先做一次：手腕（ID 1）

手腕是皮带，不用装线：
```
uv run python scripts\check_motor.py %CFG% --wrist
uv run python scripts\calibrate.py %CFG% --joints wrist --force-wrist
```
第一次运行会问硬件版本 → 输入 **2**。

### 每个手指关节重复这 6 步（例：食指 MCP，左手是 ID 8）

| # | 做什么 | 命令 | 应该看到 |
|---|---|---|---|
| 1 | 关 12V；通信线只接 ID 1 和 ID 8；按 ORCA 装配说明装好 ID 8 的腱绳 | — | — |
| 2 | 开 12V，扫描 | `uv run python scripts\configure_motor_chain.py %CFG% --scan` | 只有 ID 1、8 |
| 3 | 小幅试转（确认舵机能拉动这根线） | `uv run python scripts\check_motor.py %CFG% --motor-id 8` | 食指 MCP 轻微动 |
| 4 | 预紧：舵机先把线拉直再顶住；用棘轮扳手**顺时针**拧 ID 8 **上面**的卷线轮，听到咔哒，线紧但不硬就停，按 Ctrl+C | `uv run python scripts\tension.py %CFG%` | 线不松 |
| 5 | 标定这一个关节 | `uv run python scripts\calibrate.py %CFG% --joints index_mcp` | 弯到底、伸到底各一次 |
| 6 | **第 4、5 步再做一次**（第一次标定后线会松，官方说明就是这样），然后用滑条确认 | `uv run python scripts\manual_control.py %CFG%` | 拖 index_mcp 的滑条，手指跟着动，到两头不卡 |

### 进度表（建议按这个顺序：一根手指做完再做下一根）

| ID | `--joints` 名称 | 关节（左手） | 腱绳装好 | 预紧 | 标定 ×2 | 滑条能动 |
|---|---|---|---|---|---|---|
| 1 | `wrist` | 手腕 | —（皮带，不用腱绳） | — | ☐ | ☐ |
| 8 | `index_mcp` | 食指根部 MCP | ☐ | ☐ | ☐ | ☐ |
| 9 | `index_pip` | 食指中间 PIP | ☐ | ☐ | ☐ | ☐ |
| 7 | `index_abd` | 食指侧摆 | ☐ | ☐ | ☐ | ☐ |
| 17 | `middle_mcp` | 中指 MCP | ☐ | ☐ | ☐ | ☐ |
| 2 | `middle_pip` | 中指 PIP | ☐ | ☐ | ☐ | ☐ |
| 6 | `middle_abd` | 中指侧摆 | ☐ | ☐ | ☐ | ☐ |
| 4 | `ring_mcp` | 无名指 MCP | ☐ | ☐ | ☐ | ☐ |
| 3 | `ring_pip` | 无名指 PIP | ☐ | ☐ | ☐ | ☐ |
| 5 | `ring_abd` | 无名指侧摆 | ☐ | ☐ | ☐ | ☐ |
| 15 | `pinky_mcp` | 小指 MCP | ☐ | ☐ | ☐ | ☐ |
| 16 | `pinky_pip` | 小指 PIP | ☐ | ☐ | ☐ | ☐ |
| 14 | `pinky_abd` | 小指侧摆 | ☐ | ☐ | ☐ | ☐ |
| 10 | `thumb_cmc` | 拇指根部 CMC | ☐ | ☐ | ☐ | ☐ |
| 13 | `thumb_abd` | 拇指侧摆 | ☐ | ☐ | ☐ | ☐ |
| 12 | `thumb_mcp` | 拇指 MCP | ☐ | ☐ | ☐ | ☐ |
| 11 | `thumb_dip` | 拇指 DIP | ☐ | ☐ | ☐ | ☐ |

（ID 和名称来自官方**左手** config `orca_core/models/v2/orcahand-left/config.yaml` 的 `joint_to_motor_map`，2026-10-26 版。左右手的 ID 完全不一样，**别看网上右手的表**。）

### 不对怎么办

| 现象 | 可能原因 | 做什么 |
|---|---|---|
| 第 3 步舵机转了但手指不动 | 线没挂上、太松 | 查线的两头 |
| 第 4 步舵机一直转、停不下来（20 秒） | 线脱了或断了，卷线轮空转 | Ctrl+C，关电查线 |
| 第 5 步报 “never settled onto a hardstop” | 同上，或者线卡住 | 查线 |
| 第 5 步关节没走到头就停 | 线太紧（被电流顶住） | 用棘轮反方向松一点，重做第 5 步 |
| 手指方向反了（让它弯它伸） | 线绕反了 | 对照装配说明重绕 |

全部 17 个都打完勾以后，再把所有通信线接上，从“明天测试”的第 7 步（回中立）、第 8 步（演示）继续。

## 明天测试

每次打开新的 cmd 窗口，先运行这两行（以后的命令都用 `%CFG%` 代替那串很长的路径）：

```
cd orca_core
set CFG=orca_core\models\v2\orcahand-left\config.yaml
```

**我们的是左手**（用户 2026-10-26 确认），所以路径是 `orcahand-left`。

然后按顺序，每步通过再做下一步：

| # | 命令（复制粘贴） | 做什么 | 应该看到 | 不对怎么办 |
|---|---|---|---|---|
| 1 | `uv run python scripts\configure_motor_chain.py %CFG% --scan` | **只读**，扫描总线上所有舵机（会扫好几种波特率，要等一会儿） | ID 1–17 共 17 个，波特率 57600，手指 XC330-T288-T、手腕 XC430 | 见下面“扫描结果怎么看” |
| 2 | `uv run python scripts\check_motor.py %CFG% --wrist` | 手腕小幅来回转。第一次会问硬件版本 → 输入 **2** | 手腕动一点点 | 不动 → 看电源、皮带 |
| 3 | `uv run python scripts\check_motor.py %CFG% --motor-id 9` | 食指 PIP（左手 ID 9）小幅来回转 | 食指动一点点 | 记下现象 |
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

程序每次连接都会先试 1M、3M，再试其他波特率，最后才找到 57600。不影响使用，只是每次多等几秒。想省掉：用记事本打开 `orca_core\models\v2\orcahand-left\config.yaml`，在最上面加一行 `baudrate: 57600`，保存。

## 不要做的事

- 不要运行 `configure_motor_chain.py`（不带 `--scan`）：它是给新舵机设 ID 用的，我们的 ID 已经设好了。
- 不要加 `--baudrate`（会改舵机波特率）。
- 标定、预紧时手指附近不要放东西、不要用手挡。

## 给领导的一句话说明

ORCA 手用的是官方开源软件 orca_core（ETH Zurich，MIT 许可证），通过 U2D2 控制 17 个 Dynamixel 舵机（手指 XC330、手腕 XC430）；完成预紧和自动标定后，可以按关节角或预设手势控制。下一步计划把 U2D2 换成我们自己的 KM1M7C 板。
