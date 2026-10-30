# orca_core 代码导读：每个文件是干什么的、怎么用（左手 v2.0 版）

> 对照的是 `orcahand/orca_core` main 分支，最新提交 2026-10-26（`e7a8540`）。
> 标记：**【源码】** = 读代码确认；**【文档】** = 只来自官方 docs（`docs/` 目录作者自己说“部分过时”）；**【推测】** = Claude 的判断，没在实物上验证。

---

## 0. 先猜一下（答案在第 4 节）

你用 U2D2 接左手 v2.0，运行 `calibrate.py` 时终端问：
`Enter 2 (v2.0), 21 (v2.1), or press Enter to continue as v2.0:`

- A. 随便输，只是记录用
- B. 输 2 或直接回车都对；输 21 会让拇指 MCP/DIP 两个电机反着转
- C. 必须输 21，因为是 v2 系列最新版
- D. 输入会改写官方 `config.yaml`

<details><summary>答案</summary>

**B**。见第 4.2 节。D 也不对：它写的是 config 旁边的 `local_config.yaml`，不改 `config.yaml`。
</details>

---

## 1. 一句话：orca_core 是什么

ORCA 手的**官方 Python 控制包**：把 17 个舵机抽象成“17 个关节角度”，并提供**预紧、标定、回中立、手动滑块、演示**等现成脚本。网页版控制台 `orca_ui` 也是调它。

分四层（从上到下）【源码】：

```
scripts/、examples/      ← 你在命令行运行的东西（只有参数解析和打印，没有逻辑）
        │
OrcaHand（hardware_hand.py）  ← 关节空间 API：set_joint_positions({"index_mcp": 40})
        │   关节角 ⇄ 电机角 的换算靠 calibration.yaml + joint_to_motor_map
MotorClient（hardware/dynamixel_client.py）← 读写舵机寄存器（Sync Read/Write）
        │
pyserial → COM 口 → U2D2（或 KM1M7C 透传）→ 17 个 XC330/XC430
```

关键原理：腱绳手**没有关节角度传感器**（你的是纯电机版），软件只知道电机转了多少。所以必须先**标定**：把每个关节分别顶到两端机械限位，记下电机位置 `m_min`、`m_max`，以后按线性关系 `电机角 = m_min + (关节角 − θ_min) × 比例` 换算。
**这个线性假设在什么时候失效**：腱绳松了（同样电机角，关节转得少）、绳子打滑、或标定时被卡住没真的撞到限位。所以官方说“预紧 → 标定”要反复 2–3 次。

---

## 2. 目录和每个文件

### 2.1 你会直接运行的：`scripts/`

全部支持 `--help`；第一个参数是 config 路径。**不写就自动检测，而 U2D2 上认不出左右手，源码规定“没有左右信息就当右手”**——左手会被按右手映射驱动。所以**一定要写左手 config 路径**。【源码：`hand_factory.detect_hand()`】

| 文件 | 作用 | 会不会动 | 左手 v2.0 用不用 |
|---|---|---|---|
| `detect.py` | 自动检测：认官方控制板、看用哪个型号、端口、是否已标定 | 只读 | U2D2 没有官方控制板，会报成右手，**结果不可信**【源码】 |
| `configure_motor_chain.py` | 新舵机一个一个插上，设 ID 1–17 和波特率；`--scan` 只扫描 | 写 EEPROM | `--scan` 常用；ID 你已设好，**不要不带参数乱跑** |
| `check_motor.py` | 单个电机在当前位置附近小幅来回转，确认它能动、能拉绳 | 小幅动 | 装绳、查绳时用 |
| `tension.py` | 预紧：先自动“卷紧”一下（默认电机转 15°），然后锁住电机，你用棘轮扳手顺时针拧上线轮；Ctrl+C 结束 | 动 | **要用** |
| `guided_tension.py` | 引导式预紧（自动判断松紧） | 动 | **v2.0 会拒绝运行**（依赖 v2.1 的行程基准）【源码】 |
| `calibrate.py` | 标定：按 config 里 16 步顺序，把每个关节撞两端限位，结果写 `calibration.yaml` | 动（撞限位） | **要用**；可加 `--fingers thumb index` 或 `--joints index_mcp` 只标一部分 |
| `measure_travel.py` | 测每个关节的电机行程，写成基准 | 动 | v2.0 **用不上**（基准只在 v2.1 生效）【源码】 |
| `neutral.py` | 回中立姿势 | 动 | 要用（**没标定过会先自动标定**，见第 4.4 节） |
| `zero.py` | 所有关节回 0° | 动 | 同上 |
| `manual_control.py` | Tkinter 滑块窗口：每关节一个滑块；`--motor-space` 改成每电机一个小范围滑块（查单根绳用） | 动 | **最有用的调试工具** |
| `stress_test.py` | 拇指反复弯伸、看温度 | 动 | 修好手之后再说 |
| `setup.py` | 一条龙：3 轮“预紧 + 标定”+ 1 分钟动作测试 | 动 | 熟练后可用；第一次建议手动一步步来 |
| `check_sensors.py` / `monitor_sensors.py` / `check_encoder_signs.py` | 关节编码器、触觉传感器的检查和实时显示 | — | 你的手**没有传感器**，不用（`monitor_sensors.py` 也能看电机位置/电流/温度，可选） |

### 2.2 示例：`examples/`

| 文件 | 作用 |
|---|---|
| `main_demo.py` | 演示：张开 → 握拳 → 捏；`--demo abduction` 是手指张开收拢 |
| `demo_runner.py` | 上面那个的播放逻辑 |
| `record_angles.py` / `replay_angles.py` | 关扭矩用手摆姿势，按回车记一帧；再回放 |
| `record_continuous.py` / `replay_continuous.py` | 连续录制（默认 50 Hz）和回放 |
| `sequences/kapandji_opposition.yaml` | 拇指对指的动作序列 |
| `taxel_frames.py` | 触觉数据，你用不上 |

### 2.3 配置：`orca_core/models/`

| 文件夹 | 是什么 | 你用不用 |
|---|---|---|
| `v2/orcahand-left/` | **v2 左手，纯电机** | **就是它** |
| `v2/orcahand-right/` | v2 右手 | 不用 |
| `v2/orcahand-joint-left/` | 左手 + 关节编码器 | 不用 |
| `v2/orcahand-touch-left/` | 左手 + 指尖触觉 | 不用 |
| `v2/orcahand-full-left/` | 编码器 + 触觉都有 | 不用 |
| `v1/…` | 旧一代（3 Mbps） | 不用 |

同一个文件夹里运行后还会多出：`calibration.yaml`（标定结果）、`local_config.yaml`（版本号等本机覆盖）。

### 2.4 包内部：`orca_core/`（自己写程序时才需要看）

| 文件 | 作用 |
|---|---|
| `hand_factory.py` | `load_hand(config_path)`：**推荐入口**，按 config 选对类 |
| `hardware_hand.py` | `OrcaHand`：connect / init_joints / calibrate / tension / set_joint_positions… 核心逻辑都在这 |
| `base_hand.py` | 所有手共用的关节空间接口（抽象类） |
| `hand_config.py` | 读 config.yaml、检查字段、版本号选哪张映射表、写 `local_config.yaml` |
| `calibration.py` | `calibration.yaml` 的读写格式 |
| `joint_position.py` | 关节角容器 `OrcaJointPositions` |
| `demo_poses.py`、`data/demo_poses.yaml` | 演示姿势（用 ROM 百分比写，所以左右手通用） |
| `constants.py`、`version.py` | 控制模式编号、默认步数、波特率候选表等 |
| `hardware_hand_sensing.py` | 带传感器的几种手，你不用 |
| `maintenance/` | 预紧、标定、设 ID 等“维护流程”的真正实现（脚本只是外壳） |
| `control/` | 关节编码器闭环 PI 控制，你没有编码器，不用 |
| `kinematics/` | 正运动学（手指尖在空间哪里），可选 |
| `api/` | 用 FastAPI 把手开成 HTTP 接口，作者说还不完整 |
| `hardware/dynamixel_client.py` | Dynamixel 读写（加了总线锁，线程安全） |
| `hardware/motor_resolution.py` | 连接时探测是哪家舵机、哪个波特率 |
| `hardware/feetech*`、`mock_*` | 飞特舵机版本和测试用的假硬件 |
| `hardware/sensing/`、`tactile_client.py`、`joint_encoder_client.py`、`hand_serial_link.py` | 传感器板通信，你不用 |
| `utils/cli.py` | 所有脚本共用的参数和“连接后问版本号”的逻辑 |

### 2.5 其他

- `tests/`：单元测试（用假硬件，Windows 上 `uv run pytest` 约 3 秒跑完），可以当作“安装是否正确”的检查。
- `tools/`：维护者用的（检查下游仓库、从 URDF 提取运动学），你不用。
- `docs/`：MkDocs 文档源，**作者自己说部分过时，以代码为准**。
- `CLAUDE.md`：给 AI 的开发规则，里面的结构说明其实是最新最准的目录说明。

---

## 3. 怎么用：左手 v2.0 推荐流程

用根目录 `Start-ORCA.bat` 最省事（会 git pull 本仓库、下载/更新 orca_core、建 uv 环境、生成你的 config，然后给菜单）。手动命令版（在 `orca_core` 文件夹里）：

```bat
set CFG=orca_core\models\v2\orcahand-left\config.yaml

uv sync
uv run python scripts\configure_motor_chain.py %CFG% --scan     :: 1. 17 个都在？
uv run python scripts\check_motor.py %CFG% --motor-id 8         :: 2. 单个电机能动？（8 = 左手食指 MCP）
uv run python scripts\tension.py %CFG%                          :: 3. 预紧，拧棘轮，Ctrl+C
uv run python scripts\calibrate.py %CFG%                        :: 4. 标定
::   3、4 重复 2–3 次，直到标定后不再出现松弛
uv run python scripts\neutral.py %CFG%                          :: 5. 回中立
uv run python scripts\manual_control.py %CFG%                   :: 6. 滑块逐个关节试
uv run python examples\main_demo.py %CFG%                       :: 7. 演示
```

**重要（中指 ABD 还没修好时）**：第 4 步改成 `--fingers thumb index ring pinky`（跳过中指），第 5、7 步先别跑（原因见 4.4）。

自己写程序最小例子【源码，API 名称已核对，未在实物上运行】：

```python
from orca_core import load_hand

hand = load_hand(r"orca_core\models\v2\orcahand-left\config.yaml")
ok, msg = hand.connect()
hand.init_joints()                      # 开扭矩、设模式和电流上限；没标定过会先标定！
hand.set_joint_positions({"index_mcp": 60, "index_pip": 60})   # 单位：度
print(hand.get_joint_position())
hand.disable_torque()
hand.disconnect()
```

注意：只 `connect()` 不 `init_joints()` 就发位置，舵机会用**上电时的 Goal Current**（不是 300 mA 上限）——源码注释原话就是在提醒这个。【源码】

---

## 4. 左手 v2.0 要特别注意的 6 件事

### 4.1 左手电机 ID ↔ 关节（`orcahand-left/config.yaml`，v2.0 表）【源码】

正号 = 弯曲时电机逆时针（CCW），负号 = 顺时针（CW）。

| 手指 | ABD（外展） | MCP | PIP / DIP |
|---|---|---|---|
| 拇指 | CMC −10，abd −13 | **+12** | DIP **+11** |
| 食指 | −7 | −8 | PIP −9 |
| 中指 | −6 | −17 | PIP −2 |
| 无名指 | −5 | +4 | PIP −3 |
| 小指 | +14 | −15 | PIP +16 |
| 手腕 | −1（XC430，多圈位置模式） | | |

### 4.2 版本号：U2D2 上必须是 2，不能是 21 【源码】

- config 里有两张映射表：`joint_to_motor_map`（v2.0）和 `joint_to_motor_map_v21`。两张表**只差拇指 MCP（12）和 DIP（11）的正负号**——v2.1 左手的这两根绳反方向绕。
- `hardware_version: auto` 时，软件去问官方控制板（OH board）。**U2D2 不是这块板**，问不到，连接后会在终端问你：
  - 输 `2` 或直接回车 → 用 v2.0 表（对）。输 `2` 还会写进 `local_config.yaml`，以后不再问。
  - 输 `21` → 拇指 MCP/DIP 反着转，标定时会往反方向使劲（**错**）。输错了：删掉 config 旁边的 `local_config.yaml`。
- `Start-ORCA.bat` 生成的 config 现在直接写死 `hardware_version: 2`（第一次运行时可选 21）。

### 4.3 v2.0 不享受 v2.1 的保护功能 【源码】

在 v2.0（或版本未知）时：
- 标定只做**一遍**，不检查行程、不自动重试；
- `calibration_current_v21`（ABD 300 / MCP 500 / PIP 500 mA）**不生效**，全部用 `calibration_current: default` = **300 mA**；
- `guided_tension.py` 拒绝运行，`measure_travel.py` 测了也不用。

所以 v2.0 要靠**人眼**判断松紧：标定后某个关节动不到位、或明显比兄弟关节（四个 MCP、四个 PIP）行程短，多半是那根绳太紧或卡住了。

### 4.4 这几个脚本“没标定会自动标定” 【源码】

`neutral.py`、`zero.py`、`main_demo.py`、`stress_test.py`、`record_angles.py` 都调用 `init_joints()`，它的逻辑是：**找不到 `calibration.yaml` 就先跑完整标定**（16 步，包括中指 ABD 撞两端限位）。
中指 ABD 的结卡在手掌通道里的现在，**不要在没有 calibration.yaml 时跑这些**；先用 `calibrate.py --fingers thumb index ring pinky` 标其他手指。【推测】部分标定后 `calibrated` 可能仍为 False（中指没标），那些脚本还是会触发完整标定——修好中指前，只用 `manual_control.py` 和 `check_motor.py` 最稳妥。

### 4.5 波特率 57600 能用，但慢 【源码 + 推测】

- 自动探测先试 1 Mbps、3 Mbps，都不应答再扫其他速率，所以 57600 **最终能找到**，只是每次连接多花几秒。`Start-ORCA.bat` 的 config 已固定 `baudrate: 57600`，跳过探测。
- 57600 下 17 个舵机读一圈约 70 ms【推测，按字节数估算】，演示动作会一顿一顿。以后想更顺：`configure_motor_chain.py %CFG% --baudrate 1000000` 改舵机 EEPROM，同时 KM1M7C 固件舵机侧也要改成 1M。

### 4.6 Windows 专属 【文档】

- **COM 口独占**：Dynamixel Wizard、串口助手开着时，orca_core 会报 `PermissionError: Access is denied`。先关掉它们。
- **U2D2 的延迟**：设备管理器 → 端口 → USB Serial Port (COMx) → 属性 → 端口设置 → 高级 → **Latency Timer 改成 1**（默认 16 ms，会把控制频率压到很低）。Linux 上软件会自动改，Windows 不会。

---

## 5. 三种用法，怎么选

| 方向 | 做法 | 好处 | 代价 |
|---|---|---|---|
| A. 只用官方脚本（**主流做法，推荐先这样**） | `Start-ORCA.bat` 菜单 | 不写代码，最快让手动起来；和官方/Discord 的人说的是同一套东西 | 只能做官方设计好的动作 |
| B. 官方包 + 自己的 Python | `load_hand()` + `set_joint_positions()`，例子 `tools/orca/finger_wrist_example.py` | 自定义动作、接其他程序 | 要自己管标定状态和电流 |
| C. 网页控制台 orca_ui | 菜单 `W`，浏览器打开 | 有 3D 显示，适合给领导演示 | 多一层，出问题难查 |

---

## 6. 关键事实来源（以后细看）

- 左手配置：`orca_core/models/v2/orcahand-left/config.yaml`
- 版本号逻辑：`orca_core/utils/cli.py` 的 `settle_hardware_version()` / `prompt_hardware_version()`
- 自动标定触发：`orca_core/hardware_hand.py` 的 `init_joints()`
- v2.0 无行程基准：`CLAUDE.md` “Configuration” 一节，`docs/pages/getting-started-docs/setting-up-config.md` 第 8 节
- 波特率探测：`orca_core/hardware/motor_resolution.py` 的 `trial_probe()`，`orca_core/constants.py` 的 `MOTOR_BAUD_RATES`
- Windows：`docs/pages/getting-started-docs/windows.md`
