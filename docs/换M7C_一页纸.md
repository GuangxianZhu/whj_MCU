# 今天把 U2D2 换成 M7C（KM1M7C）：一页纸（官方命令版）

> **2026-11-04 结果：KM1M7C 连接成功，手控制成功。** 过程中用户在电脑上用另一个 Claude 做了修改（固件 / config / 命令？），内容待补充到下面“实际改动”一节。
>
> 前提：U2D2 下预紧、再标定、中立、零位、手势都通过了（11-04）。
> 原理和更多排错见 `docs/下一步_预紧到换KM1M7C.md` 第 ③④ 节。下面 `<whj_MCU>` 是你电脑上本仓库的文件夹。
> 所有命令都在 **orca_core 文件夹**里运行，先 `cd` 进去。

---

## 第 1 步：U2D2 还插着，先记基准（只读，不会动）

```bat
cd <orca_core 文件夹>
set CFG=orca_core\models\v2\orcahand-left\config.yaml
uv run python <whj_MCU>\tools\orca\bus_timing.py %CFG%
```

把整段输出记下来，或者拍照发给 Claude。重点看两行：

- **Return Delay**（每个舵机）：
  - 500：出厂值，时间很宽裕；
  - **20**：用 orca_core 设过，M7C 固件必须用 **TC（发送完成）** 标志切 TXEN。
- **平均 / 最大 ms、失败次数**：等一下拿来和 M7C 比。

## 第 2 步：做一份写死 COM 和 57600 的 config

**为什么必须做**：M7C 的 USB 虚拟串口不管电脑设多少波特率。官方 config 让 orca_core 自动探测，它会误以为是 1 Mbps，然后每次读都超时。详细原因见主文档“坑 1”。

1. 插上 M7C 的 USB，看它是哪个 COM：

   ```bat
   uv run python <whj_MCU>\tools\orca\make_config.py --list
   ```

2. 生成 config（把 COM7 换成你看到的）：

   ```bat
   uv run python <whj_MCU>\tools\orca\make_config.py . --side left --port COM7 --baud 57600 --hw 2
   ```

3. 把标定结果搬过去，然后改用新 config：

   ```bat
   copy orca_core\models\v2\orcahand-left\calibration.yaml <whj_MCU>\tools\orca\my_hand\
   set CFG=<whj_MCU>\tools\orca\my_hand\config.yaml
   ```

腱绳没动，标定结果和转接器无关，所以**不用重新标定**。

## 第 3 步：换线

1. **先关 12V 电源**。
2. 拔掉 U2D2（USB 和 3P 线都拔）。总线上不能有两个主机。
3. PHB 来的 3P 线只接面包板的 **GND（第 2 列）和 DATA（第 4 列）**，**12V 不接面包板**。
4. 确认 M7C 已经烧好你的透传固件：UART5 ⇄ UART2，舵机侧 **57600**。
5. 关掉串口助手和 Dynamixel Wizard。
6. 打开 12V。

## 第 4 步：小步验收（一步过了再做下一步）

| # | 命令 | 合格 | ✓ |
|---|---|---|---|
| K1 | `uv run python <whj_MCU>\tools\orca\bus_timing.py %CFG%` | 失败 0 次，耗时和第 1 步差不多 | |
| K2 | `uv run python scripts\configure_motor_chain.py %CFG% --scan` | 17 个都在 | |
| K3 | `uv run python scripts\check_motor.py %CFG% --motor-id 8` | 食指 MCP 小幅来回 | |
| K4 | `uv run python scripts\manual_control.py %CFG% --motor-space` | 每个电机跟手 | |
| K5 | `uv run python scripts\neutral.py %CFG%` | 和 U2D2 时一样 | |
| K6 | `uv run python scripts\manual_control.py %CFG%` | 17 个关节都正常 | |
| K7 | `uv run python examples\main_demo.py %CFG%`，再加 `--demo abduction` 跑一次 | 两个演示都完成 | |
| K8 | `uv run python scripts\calibrate.py %CFG%`，然后 `uv run python <whj_MCU>\tools\orca\compare_travel.py <whj_MCU>\tools\orca\my_hand` | 标定跑完；行程和 U2D2 时差不多 | |

## 卡住时先看这里

| 现象 | 先查 |
|---|---|
| K1/K2 一个都没有 | COM 对不对；固件舵机侧是不是 57600；GND 有没有共地 |
| 能找到但时有时无 | 第 1 步的 Return Delay 是不是 20，固件 TXEN 是不是用 TC 切 |
| `PermissionError: Access is denied` | 串口助手、Wizard 或另一个终端占着 COM |
| 想退回 U2D2 | 关 12V → 换回 U2D2 → `set CFG=` 改回官方路径，一切照旧 |

## 结果（填这里，或发给 Claude）

| | Return Delay | 平均 / 最大 ms | 失败次数 |
|---|---|---|---|
| U2D2 | | | |
| M7C | | | |

## 实际改动（2026-11-04，待用户补充）

- （用户明天告知）
