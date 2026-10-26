# ORCA Hand 软件调研：哪些控制手指的部分能拿来用

调研日期：2026-10-26
对象：GitHub `orcahand/orca_core`（main，最新提交 2026-10-23），MIT 许可证（可以抄、改，保留版权声明即可）。
论文：arXiv 2504.04259（ORCA: An Open-Source, Reliable, Cost-Effective, Anthropomorphic Robotic Hand）。

---

## 一句话结论

**ORCA v2 和我们的腱绳手指几乎是同一套东西**：舵机就是 XC330-T288-T（代码里型号表写的 1220 = XC330-T288-T），每个关节一个舵机，屈、伸两根线，Protocol 2.0。所以它最值得拿的不是整个软件包，而是三样东西：

1. **自动标定**：限流撞两头限位 → 记下舵机两端位置 → 线性换算关节角。可以直接代替阶段 1 里“扭矩关、用手扳、读 P_open/P_close”。
2. **预紧（张紧）的做法和判断标准**：舵机在电流限制位置模式下“顶住”，再拧棘轮卷线轮收线；行程变短、电流变大 = 线太紧。
3. **XC330 的现成参数**：电流上限、默认电流、手势用“ROM 的百分比”表示等。

---

## 1. ORCA 的整体结构（和我们对照）

| 项目 | ORCA v2 | 我们（whj_MCU） |
|---|---|---|
| 舵机 | XC330-T288-T ×17（手腕另外用皮带） | **一样：17 个电机，手腕和手指买的都和 ORCA 一样**（用户 2026-10-26 告知）；面包板上试过的 ID 0–3 以后要按 ORCA 改成 1–17 |
| 每关节 | 1 个舵机，屈/伸两根线（0.4 mm 编织鱼线） | 1 个舵机，两根线反向绕同一个卷线轮（B 方案） |
| 卷线轮 | 每个舵机上下两个 spool，上面那个带**棘轮**，可以不拆线直接拧紧 | 卷线轮已有，没有棘轮 |
| 关节传感器 | v2 没有（只靠舵机位置推算）；新版 v2.1 可选关节编码器 | 没有 |
| 控制模式 | `current_based_position`（= 地址 11 写 5，电流限制位置控制） | 阶段 1 也用模式 5 |
| 通信 | PC → U2D2 → 舵机，1 Mbps，Python | PC → **KM1M7C（当 U2D2 用）** → 舵机，现在 57600 |
| 软件 | Python 包 `orca_core`（约 2.1 万行），另有图形界面 `orca_ui` | `tools/dxl_packet.py` + Keil 固件 |

> 证据强弱：舵机型号、控制模式、地址、电流值来自源码（**确定**）。“上下两个 spool 分别绕屈线和伸线”是从文档“拧上面的 spool、下面的 spool 被舵机顶住”推断的（**推测**，论文没说清是一个还是两个卷线轮）。

---

## 2. 能拿来用的部分（按用处排序）

### ① 自动标定：撞限位找两端（最值得用）

源码：`orca_core/maintenance/calibration_routine.py` 的 `_drive_step()`；换算在 `orca_core/hardware_hand.py` 的 `_motor_to_joint_pos()` / `_joint_to_motor_pos()`。

**做法**（每个关节两步：先弯到底 flex，再伸到底 extend）：

1. 设电流上限（XC330 默认 300 mA；v2.1 的 MCP/PIP 用 500 mA，侧摆 300 mA）。
2. 打开扭矩，每次让目标位置**相对当前位置**走一小步（0.15 rad ≈ 8.6°）。
3. 每步读当前位置，连续 10 次变化都 < 0.01 rad（≈ 0.6°）→ 认为撞到机械限位（舵机被电流限住，转不动了）。
4. **先关扭矩再读位置**（这样读到的是线不受力时的位置，不会把“线被拉长”算进去），记为这一头的限位。
5. 两头都有了：
   - 舵机行程 Δm = m_max − m_min
   - 关节行程 Δθ = θ_max − θ_min（ORCA 用 CAD 里的设计值，例如食指 MCP −25°～100°）
   - 传动比 ρ = Δm / Δθ
6. 以后控制：**m = m_min + ρ × (θ − θ_min)**，反过来 θ = θ_min + (m − m_min) / ρ。

**它还带的保护**（我们可以照抄思路）：
- 超时（线断了、卷线轮空转就永远停不下来）→ 放弃这一方向。
- 舵机有 Hardware Error（过热、过载）就跳过，不把“没动”误当成“到限位”。
- 测出的行程比基准值短很多 → 说明中途卡住或**线太紧**，提高电流重来一次。

**对我们的意义**：阶段 1 第 4 步“扭矩关用手扳读 P_open/P_close”可以换成这个自动版。原理一样（找两端），但用电流限住、一小步一小步走，重复性比手扳好。我们用串口助手也能手动模拟：模式 5 + Goal Current 60 mA，Goal Position 每次 +100（≈ 8.8°），Read 地址 132，位置不再变就是到头。

**这个方法依赖的假设**（在这些条件下会失效）：
- 关节真的有**硬限位**（机械挡块）。没有挡块的话，线会被一直拉，直到电流上限，测到的是“拉紧到某个力的位置”，不是关节角。
- 腱绳**不打滑、不明显伸长**。鱼线会慢慢变松，所以 ORCA 要求“用久了、松了、重新拧紧以后都要重新标定”。
- 关节角和舵机角是**线性**的（卷线轮半径和关节滑轮半径固定）。如果线绕在曲柄上（舵盘孔）就不是线性的。

### ② 预紧（张紧）的做法和“紧不紧”的判断

源码：`orca_core/maintenance/tensioning.py`、`guided_tension.py`；文档 `docs/pages/getting-started-docs/initial-tensioning-and-calibration.md`。

- 舵机在模式 5 下先往正方向（逆时针）转约 15°，把线拉直，然后**原地顶住**（目标位置 = 实际到达的位置，避免一直有误差、一直耗电流）。
- 人用棘轮扳手顺时针拧上面的 spool，听到“咔哒”就是在收线。
- 标准：**线要紧、不松，但不能拧过头，允许一点点余量**。
- 新装好的手：标定 → 拧紧 → 再标定，重复 2–3 次，直到标定后不再出现松线。
- 线太紧的两个信号：标定时**行程变短**（没走到挡块就被电流顶住），**驱动电流比别的关节高很多**。

**对我们的意义**：对应阶段 1 第 7 步“调预紧/查空转”。没有棘轮的话，可以先用“松开卷线轮螺丝 → 拉紧一根 → 重新拧螺丝”的土办法；以后打印卷线轮时考虑加棘轮。判断紧不紧可以直接用 ORCA 的两个信号，比凭手感客观。

### ③ XC330 的参数参考

源码：`orca_core/hardware/dynamixel_client.py`、`config.yaml`。

| 项目 | ORCA 的值 | 说明 |
|---|---|---|
| Current Limit（地址 38）范围 | 0–910 mA | XC330-T288-T，1 mA/单位 |
| 平时最大电流 | 300 mA | “300 mA 能把拉紧好的手的每个关节推到限位” |
| 标定电流 | 300 mA（v2.1：MCP/PIP 500 mA） | |
| 抓力测试 | 600 mA | 论文里的测试值 |
| 空载速度 | 约 70 rpm | |
| 波特率 | 1 Mbps | 我们是 57600，够用（只有 4 个舵机） |
| 加速通信 | Return Delay Time（地址 9）= 0、Status Return Level（地址 68）= 1、Fast Sync Read | 17 个舵机时才明显；我们现在不需要 |

我们阶段 1 的 60 / 100 / 150 mA 比 ORCA 保守，**先用小的是对的**（我们的结构是新做的，没验证过强度）。

**传动比参考**（Claude 用 ORCA 的配置算的）：食指 MCP 关节转 125°，舵机转约 139°，ρ ≈ 1.1；PIP 关节 122°，舵机 131°，ρ ≈ 1.07。也就是说 ORCA 的卷线轮半径和关节滑轮半径差不多（r_s ≈ r_j）。我们量出 r_s、r_j 后可以对比一下。

### ④ 手势用“ROM 百分比”写

源码：`orca_core/data/demo_poses.yaml`。

手势不写舵机位置，而写“这个关节在自己范围里的几成”：0 = 一头，1 = 另一头。例如握拳 `index_mcp: 0.85, index_pip: 0.9`，张开 `0.15 / 0.1`。好处：重新标定、换线以后手势不用改。
对我们：`docs/一根手指.md` 里的手势现在写的是 2048/3072 这种绝对位置，以后可以改成百分比，由 P_open/P_close 换算。

### ⑤ 暂时用不上的部分

- `control/joint_loop.py`、`joint_controller.py`：PC 上 100 Hz 的外环 PI，要有**关节编码器**才有意义（v2.1）。我们没有关节传感器，先不用。
- `kinematics/`：整只手的正运动学，现在一根手指用不上。
- `hardware/feetech*`：飞特舵机驱动，和我们无关。
- `tactile_client.py`、`sensing/`：指尖触觉传感器，以后加传感器时可以参考数据格式。

---

## 3. 用 KM1M7C 代替 U2D2 跑 orca_core（2026-10-26 更新）

### 问：这个 Python 包是不是只能在 U2D2 上用？

**不是。** orca_core 底层用的是 ROBOTIS 官方的 `dynamixel_sdk`，它只认“一个串口”（Windows 上的 COMx），往里写 Protocol 2.0 的字节、再读回应答。它不关心串口后面是 U2D2 还是别的东西。我们的 `firmware/bridge/` 本来就是按“透明转发”设计的（PC 发什么包就原样上总线，舵机回什么就原样回 PC），所以原理上 KM1M7C 可以当 U2D2 用。

和 U2D2 有关的只有一处：**自动找串口**。它按 USB 厂商号（VID）找，只认 FTDI `0403`（U2D2）和 `16D0`。KM1M7C 的虚拟串口 VID 不一样，所以 `port: auto` 找不到——**在 config.yaml 里直接写 `port: COM5` 就绕过去了**（源码 `utils/utils.py` 的 `auto_detect_port`，确定）。

### 要满足的条件（按重要程度）

| # | 条件 | 现状 | 证据 |
|---|---|---|---|
| 1 | config.yaml 写死 `port`、`motor_type: dynamixel`、`baudrate` | `tools/orca/make_config.py` 自动写好 | 源码，确定 |
| 2 | **`baudrate` 必须等于转发固件舵机那一侧的波特率** | 现在 57600 | 推理，见下 |
| 3 | 转发固件能装下 17 个舵机的大包 | **已改**：`bridge.h` 的 `BRIDGE_MAX_PACKET` 128→320、`PC_RX_BUF` 256→1024、`REPLY_BUF` 512→1024；电脑上测试全过 | 计算 + 测试 |
| 4 | 转发固件支持的指令：Ping、Read/Write、Sync Read/Write、Fast Sync Read（0x8A）、Reboot | 都支持（`reply_kind()`） | 源码，确定 |
| 5 | 时序：PC 端的超时不能比“舵机全部回完 + 转发”短 | 57600 勉强够，1 Mbps 宽裕 | 计算，见下 |
| 6 | 固件真的在 KM1M7C 上跑起来 | **还没做**（模板里的 TODO 要填 SDK） | — |

**为什么第 2 条最要紧**：KM1M7C 的 USB 虚拟串口不管 PC 要求什么波特率（USB 本身没有波特率），舵机那一侧是固件里写死的。所以 orca_core 以为自己在用 1 Mbps，实际总线上是 57600。如果不写死，它会去扫 1M、3M……扫描结果里的“波特率”一栏全是假的。更危险的是：**不要运行 `configure_motor_chain.py --baudrate 1000000`**，它会把舵机改成 1M，而固件还在 57600，就再也连不上了（要用 U2D2 + Wizard 救回来）。我们写死 57600 以后，`configure_motor_chain.py` 会按 57600 设置舵机，前后一致。

> 推测：如果 KM1M7C 板上的“USB 虚拟串口”其实是板载调试器（Nu-Link）转出来的一路真 UART，那么 PC↔MCU 这段也有真实波特率，要和固件里 PC 那一侧的 UART 设置一致。要看板子手册确认。

### 时序估算（Claude 计算，没有实测）

一次读 17 个舵机的位置+速度+电流（Sync Read，每个应答 21 字节）：

| 总线波特率 | 总线上用时 | 转发固件多等 | dynamixel_sdk 的超时 | 余量 | 控制频率上限 |
|---|---|---|---|---|---|
| 57600 | 约 67 ms | 3 ms（等总线安静） | 约 96 ms | 约 25 ms，**偏紧**（USB 延迟大时可能超时） | 约 10 Hz |
| 1 Mbps（ORCA 默认） | 约 4 ms | 3 ms | 约 38 ms | 很宽裕 | 约 100 Hz |

原因：我们的转发固件是“收齐全部应答再一起发给 PC”，而 U2D2 是边收边发。所以舵机越多、波特率越低，等得越久。

**建议**：先用 57600 把整套流程跑通（标定、预紧、手势都不怕慢）；以后要做流畅的遥操作，再把固件和舵机一起改成 1 Mbps（要确认 KM1M7C 的 UART 能跑 1 Mbps，241 和 TXB0104 速度没问题）。

### 还要注意

- **ID**：ORCA 的配置是 ID 1–17（右手：手腕 1、食指 PIP 2、MCP 3……见 config.yaml 的 `joint_to_motor_map`，负号表示方向反）。面包板上试过的 ID 0–3 要重新分配：用菜单 3（`configure_motor_chain.py`）一次插一个舵机，它会自动改 ID。
- **硬件版本**：我们没有 ORCA 的控制板（OH board），程序问不到是 v2.0 还是 v2.1，第一次运行会让你选（2 或 21）。要按你买的零件版本选，选错了标定参数会不对。
- **电源**（估算）：17 个舵机平时上限 300 mA，标定时 MCP/PIP 可能到 500 mA。全部顶住时约 5 A 以上，适配器建议 8 A 以上；按之前的经验（JST EH 约 3 A），分几条链插到 PHB 的不同口，不要一条菊花链串 17 个。具体以 PHB 和适配器的额定值为准。
- **Status Return Level**：orca_core 默认不改（保持 2，每个写入都有应答），和转发固件的设计一致。如果以后按它的“加速”文档改成 1，转发固件每次写入会多等 10 ms，要一起改固件。

### 一键启动：根目录 `Start-ORCA.bat`

双击后它会：
1. `git pull` 更新 whj_MCU 的 main；
2. 下载（第一次）或更新 `orca_core` 到 `tools/orca/orca_core`（不进我们的仓库）；
3. 用 `uv` 装好 Python 环境（没装 uv 会提示安装命令）；
4. 第一次运行：列出所有串口，让你输入 KM1M7C 的 COM 口、左/右手、波特率，生成 `tools/orca/my_hand/config.yaml`（标定结果 `calibration.yaml` 也存在这里）；
5. 菜单：

| 选项 | 做什么 | 会不会动 |
|---|---|---|
| 1 | 扫描总线，列出所有能应答的舵机 | 只读 |
| 2 | 手动控制，每个**舵机**一个滑条（腱绳调试用） | 会动 |
| 3 | 设置舵机链：一次插一个，自动改 ID 1–17 | **写 EEPROM** |
| 4 | 单个舵机来回转一下 | 会动 |
| 5 | 预紧腱绳 | 会动 |
| 6 | 自动标定（撞限位） | 会动 |
| 7 | 回到中立姿势 | 会动 |
| 8 | 手动控制，每个**关节**一个滑条（标定以后） | 会动 |
| 9 | 改 COM 口 / 左右手 / 波特率 | — |

**建议顺序**：先用面包板上已经通的 1 个舵机试“1 扫描”，确认 KM1M7C 转发能被 orca_core 认出来 → 再装手、按 3 设 ID → 5 预紧 → 6 标定 → 5、6 重复 2–3 次 → 7、8。

### 只接 1 个舵机，用 ORCA 软件自检需要什么（2026-10-26）

| # | 需要 | 现状 | 说明 |
|---|---|---|---|
| 1 | KM1M7C 上有**自动切 DIR 的转发固件** | **有了**：用户自己写的透传固件（2026-10-26），UART5 ⇄ UART2，GPIO 控制 TXEN，在自己电脑上试成功 | 条件见下面“用户的透传固件” |
| 2 | 面包板 + PHB 12V 供电 | 已有，经 PHB 驱动 XC330 已成功 | 不用改 |
| 3 | 舵机 **ID = 1**（或 17） | 面包板上是 0–3 | 连接时 orca_core 只 ping config 里**第一个和最后一个** ID（1 和 17）来确认总线有人（`dynamixel_client.py` 的 `probe`，确定）。只接一个 ID 3 的舵机会连不上。新舵机出厂就是 ID 1 |
| 4 | 舵机波特率 = 57600 | 出厂就是 | 和固件、config 一致 |
| 5 | PC：Git、uv | `Start-ORCA.bat` 会检查、提示 | 第一次输入 COM 口、right、57600 |

注意：右手配置里 **ID 1 是手腕**。一个 XC330 设成 ID 1 时，orca_core 会把它当手腕（多圈位置模式 4），`check_motor` 只在当前位置附近小幅来回转，没有危险；正式装手时再按菜单 2 分配。扫描（菜单 1）只扫 ID 1–40，**ID 0 扫不到**。其他 16 个 ID 没接，orca_core 会当成“缺席舵机”跳过（有相关测试 `test_absent_motors.py`，推测能正常连上，没实测）。

自检顺序：菜单 1 扫描（只读，应该看到 ID 1，型号 XC330-T288-T；同一个舵机在不同波特率下重复出现是正常的，见上文）→ 菜单 3 输入 1（小幅来回转）→ 菜单 14 舵机滑条。

固件还没跑通之前的另一条路：**用 U2D2 直接接**（PC → U2D2 → PHB → 舵机），config 里 `port` 改成 U2D2 的 COM 口。这样先确认 ORCA 软件这边没问题，之后换 KM1M7C 出了问题就只可能在固件。

### 用户的透传固件（UART5 ⇄ UART2 + GPIO TXEN，2026-10-26）

用户自己写的固件：PC 一侧 UART5，舵机一侧 UART2，GPIO 控制 TXEN（= 我们的 DIR）。它是**逐字节透传**，不是 `firmware/bridge/` 那样“收齐一整包再转发”。所以：
- 上面“时序估算”里“转发固件多等 3 ms、收齐再发”那部分**不适用**，延迟只有几个字节时间，比 bridge 好。
- `bridge.h` 加大缓冲区的修改只影响 `firmware/bridge/`，和用户的固件无关。

orca_core 能用它的条件（Claude 推理，按风险排序）：

| # | 条件 | 为什么 |
|---|---|---|
| 1 | **最后一个字节的停止位发完后 20 µs 内把 TXEN 拉回 0** | 菜单 2（`configure_motor_chain.py`）给每个舵机写 Return Delay Time（地址 9）= 20 µs（`constants.py` 的 `DYNAMIXEL_RETURN_DELAY_TIME_US`，确定）。出厂是 500 µs。TXEN 放晚了，舵机应答的头几个字节会被吃掉。用“发送完成（TC）”中断或轮询 TC 标志切换就够快；用“发送缓冲区空（TXE/THRE）”就会早一个字节，用固定延时或主循环里慢慢查就可能太晚 |
| 2 | 两个方向都转：UART2 收到的字节 → UART5 发给 PC | orca_core 每次读都要收应答 |
| 3 | UART5 和 UART2 波特率相同（都是 57600），或 UART5 更快 | 逐字节透传没有大缓冲，PC 一侧慢了会丢字节。如果 UART5 是接板载 USB 转串口（如 Nu-Link VCOM），这一段的波特率是真的，PC 端设置要和它一致 |
| 4 | 一包中间 PC 的字节断开一下（USB 分批到达）时，TXEN 中途切回 0 也没关系 | 舵机要收齐整包、算完 CRC 才应答，中途短暂切换不会有冲突（推测） |

自检建议：先用 **DYNAMIXEL Wizard 2.0** 接 KM1M7C 的 COM 口扫描、看 Present Position 曲线——Wizard 和 orca_core 用的是同一种收发方式，Wizard 正常，orca_core 基本就正常。

如果条件 1 不确定：菜单 2 设完 ID 以后，可以把地址 9 改回 250（= 500 µs，EEPROM，要先关扭矩）：`python tools/dxl_packet.py` 生成写 1 字节的包。代价是 17 个舵机读一轮慢约 8 ms，57600 下影响不大。

### 方向调整

之前推荐的是“只借思路”。既然零件和 ORCA 一模一样，现在**主线改成直接跑 orca_core**（原方向 C），只把 U2D2 换成 KM1M7C。手工发 HEX（原方向 A）留作 KM1M7C 固件还没跑通时的备用。

## 4. 设定类和控制类程序一览（2026-10-26 更新：安装方式和 ORCA 一样）

用户告知：我们的安装（机械结构、腱绳、手腕）和 ORCA 一样，所以下面这些程序**原样就能用**，只要换成我们的 config.yaml（`Start-ORCA.bat` 自动处理）。“菜单”一栏是 `Start-ORCA.bat` 里的编号。

调研范围：`orcahand/orca_core`（命令行程序 + Python 库，2026-10-23 版）和 `orcahand/orca_ui`（网页控制台，2026-10-21 版），都是 MIT 许可证。

### 4.1 设定类（装好以后第一次用、以后保养）

| 菜单 | 程序 | 做什么 | 手指 / 手腕 | 我们能不能用 |
|---|---|---|---|---|
| 1 | `configure_motor_chain.py --scan` | 扫描总线，列出所有能应答的舵机（ID、型号） | 都有 | 能。波特率一栏不准（见第 3 节） |
| 2 | `configure_motor_chain.py` | **新手装机**：一次插一个舵机，自动改成 ID 1–17，设 Return Delay；中断了可以接着做 | 都有 | 能。波特率按 config 写死的 57600 |
| 3 / 4 | `check_motor.py --motor-id N` / `--wrist` | 让一个舵机在当前位置附近小幅来回转，确认它能动、能拉动腱绳 | 手指 / 手腕 | 能 |
| 5 | `tension.py` | 预紧：舵机先把线拉直，再原地顶住，人用棘轮扳手拧上面的卷线轮，拧完按 Ctrl+C | 只有手指（手腕是皮带，不用） | 能 |
| 6 | `calibrate.py` | 自动标定：按 config 的 16 步顺序把每个关节撞到两头限位，存进 `calibration.yaml`。可以加 `--fingers index` 或 `--joints index_mcp` 只标一部分 | 都有 | 能 |
| 7 | `calibrate.py --joints wrist --force-wrist` | 只重新标定手腕（手腕标过一次以后默认跳过） | 手腕 | 能 |
| 8 | `setup.py` | **整套装机向导**：预紧 → 标定，重复 3 轮，中间做 1 分钟开合测试，最后检查 | 都有 | 能，推荐新装好时用 |
| — | `measure_travel.py` | 量每个关节两限位之间舵机转了多少度，存成基准（以后标定时用来发现“线太紧、没走到头”） | 都有 | 只对 v2.1 有意义 |
| — | `guided_tension.py` | 有引导的预紧：反复“回中 → 查行程 → 拧紧”直到每根线都合格 | 手指 | 只有 v2.1 |
| — | `check_sensors.py`、`monitor_sensors.py`、`check_encoder_signs.py`、`detect.py` | 关节编码器、指尖触觉、ORCA 控制板的检查 | — | **用不上**：我们没有 ORCA 控制板和这些传感器 |

### 4.2 控制类（标定以后动手和手腕）

| 菜单 | 程序 | 做什么 |
|---|---|---|
| 11 | `neutral.py` | 回到 config 里的中立姿势（`neutral_position`） |
| 12 | `zero.py` | 所有关节回 0° |
| 13 | `manual_control.py` | 电脑上的滑条，**每个关节一个**（含手腕），带扭矩开关 |
| 14 | `manual_control.py --motor-space` | 滑条**每个舵机一个**，只在当前位置附近小范围动；不需要标定，调腱绳时用 |
| 15 | `main_demo.py --demo main` | 演示：张开 → 握拳 → 捏，循环 3 次 |
| 16 | `main_demo.py --demo abduction` | 演示：手指张开/并拢 |
| 17 | `stress_test.py` | 张开/握拳反复循环，同时看舵机温度（检查散热、过载） |
| 18 | `record_angles.py` | **示教**：扭矩关掉，用手摆好姿势，按 Enter 记一个点，存成 yaml |
| 19 | `replay_angles.py` | 回放上面记的点（可以循环、平滑过渡） |
| — | `record_continuous.py` / `replay_continuous.py` | 连续录制/回放（按频率记录，而不是一个点一个点） |
| 20 | `tools/orca/finger_wrist_example.py`（**我们自己的**） | 最小示例程序：食指弯曲 → 手腕左右 → 握拳（用 ROM 百分比）→ 读回角度 → 回中立。自己写程序时复制这个改 |

### 4.3 网页控制台 orca_ui（菜单 W）

一个浏览器里的图形界面（`http://localhost:5001`），把上面大部分功能做成了按钮，还多了：
- **Dashboard / 3D View**：实时 3D 手模型，跟着真手动；舵机健康状态一眼看到；右上角红色 **E-STOP**（停止一切、关扭矩）。
- **Setup**：预紧、标定的向导页面（手腕可以单独勾选重标）。
- **Poses**：预设姿势、录制和回放轨迹、编辑路点。
- **Motors**：每个舵机的温度、电流实时曲线；控制参数（PID、速度曲线）可以边回放边调。
- **Teleop**（还没做完）：用摄像头（MediaPipe）、手套、Apple Vision Pro 遥控。
- **MCP 服务器** `orca-ui-mcp`：让 Claude Code 这类 AI 直接读状态、摆姿势（有安全确认）。

我们怎么用：`Start-ORCA.bat` 用 `--config` 把我们的 config.yaml 交给它，里面写死了 COM 口，所以它不会去找 U2D2（源码 `orca_ui/hand/detection.py` 的 `_overrides`：config 里写了 port 就直接用，确定）。

注意：
- orca_ui 自带一份 PyPI 上的 orca_core（要求 0.10.x），和菜单 1–20 用的 `tools/orca/orca_core` 是**两份**，标定文件都存在 `tools/orca/my_hand/` 里共用。
- orca_ui 的 **`--bare` 模式**（裸舵机扫描、改 ID/波特率）**不要通过 KM1M7C 用**：它默认按 1M 扫描、可以改舵机波特率，和第 3 节说的问题一样。改 ID 用菜单 2。
- 57600 下控制频率约 10 Hz，网页里的 3D 跟随和实时曲线会有点卡，功能不受影响（推测）。

### 4.4 手腕要特别注意的地方（源码确定）

- 手腕舵机是 **XC430**（`constants.py`：Dynamixel 手腕 XC430、手指 XC330），用**皮带**传动，不是腱绳。
- 手腕用**扩展位置模式**（Operating Mode 4，可以转多圈），手指用模式 5（电流限制位置）。程序自动设置。
- XC430-T240BB-T **没有 Goal Current 寄存器**（代码里 `MODELS_WITHOUT_CURRENT_CONTROL = {1080}`），不能用电流限力；标定时改用限制 PWM 输出（`WRIST_PWM_RETRY_SCALE`），超过基准行程会放弃，降低 PWM 再试。
- 手腕标定一次以后会记 `wrist_calibrated: true`，以后默认跳过；装拆过皮带要用菜单 7 重标。
- 右手配置里手腕是 ID 1，`-1` 表示方向反；关节范围 −65°～35°。

### 4.5 自己写程序用到的 Python 函数

都在 `OrcaHand` 上（`base_hand.py`、`hardware_hand.py`），示例见 `tools/orca/finger_wrist_example.py`：

| 函数 | 用途 |
|---|---|
| `load_hand(config_path=...)` / `load_hand(mock=True)` | 建一只手（真的 / 模拟的） |
| `connect_hand(hand)`（`orca_core.utils.cli`） | 连接；第一次会问硬件版本 2 / 21 |
| `hand.init_joints()` | 没标定就先标定，然后回中立 |
| `hand.set_joint_positions({"wrist": -30, "index_mcp": 80}, num_steps=50, step_size=0.02)` | 关节角（度）；自动夹到 ROM 以内；分 50 步平滑走 |
| `hand.pose_from_fractions({...})` | 用 ROM 百分比生成姿势 |
| `hand.get_joint_position().as_dict()` | 读当前关节角 |
| `hand.set_neutral_position()` / `set_zero_position()` | 回中立 / 回 0 |
| `hand.enable_torque()` / `disable_torque()` / `set_max_current(300)` | 扭矩开关、电流上限 |
| `hand.get_motor_temp()` / `get_motor_current()` | 温度、电流 |
| `hand.tension()` / `hand.calibrate()` | 在自己的程序里调用预紧、标定 |
| `orca_core/api/api.py` | 现成的 HTTP 接口（FastAPI）：`/connect`、`/joints/position`、`/calibrate` 等，别的语言也能控制 |

> 示例程序只对照源码核对过函数名和参数，**没有运行过**（这边不能安装下载的包）。第一次建议先在你电脑上跑 `--mock`（模拟手，不用硬件）：`uv run --project tools\orca\orca_core python tools\orca\finger_wrist_example.py --mock`。

## 5. 关键文件索引（以后要细看时）

| 文件 | 内容 |
|---|---|
| `orca_core/models/v2/orcahand-right/config.yaml` | 关节名、舵机 ID 对应（负号 = 方向反）、关节范围、标定顺序、电流 |
| `orca_core/maintenance/calibration_routine.py` | 自动标定（`_drive_step` 是核心循环） |
| `orca_core/hardware_hand.py`（1469–1531 行） | 舵机位置 ↔ 关节角换算 |
| `orca_core/maintenance/tensioning.py` | 预紧流程 |
| `orca_core/hardware/dynamixel_client.py` | XC330 地址表、电流上限、型号表 |
| `orca_core/data/demo_poses.yaml` | 手势（ROM 百分比） |
| `docs/pages/orca-core-docs/latency-optimization.md` | 通信加速三招 |
| `orca_core/utils/utils.py`（`auto_detect_port`）、`constants.py`（`KNOWN_VIDS`） | 自动找串口只认 U2D2 的 VID |
| `scripts/configure_motor_chain.py` | 一个一个设舵机 ID、波特率、Return Delay |

来源：
- https://github.com/orcahand/orca_core
- https://github.com/orcahand/orca_ui
- https://arxiv.org/html/2504.04259v2
