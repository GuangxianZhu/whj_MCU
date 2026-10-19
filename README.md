# whj_MCU

KM1M7C 通过 TXB0104 和 74LVC2G241 控制 XL330 舵机的通信实验。

```
PC ──USB── KM1M7C (3.3V IO) ⇄ TXB0104 (3.3V↔5V) ⇄ 74LVC2G241 (5V, TX/RX 合成 DATA) ⇄ XL330
```

## 从这里开始

换新对话继续做时，先让 Claude 读 [`HANDOFF.md`](HANDOFF.md)。


1. **硬件**：[`docs/breadboard/README.md`](docs/breadboard/README.md)。电路图、按实际面包板画的布局、逐根接线清单、上电前检查、物料、排查表。交互版是 [`docs/breadboard/xl330_breadboard.html`](docs/breadboard/xl330_breadboard.html)，下载后用浏览器打开，可以逐根打勾、点一行高亮对应的线。
2. **软件**：[`firmware/README.md`](firmware/README.md)。DYNAMIXEL Protocol 2.0 驱动，移植到 KM1M7C 只需实现 5 个函数（DIR 引脚和 UART），附第一次通信测试流程和电脑上可跑的单元测试。
3. **排查**：先做 [`docs/breadboard/快速检查.md`](docs/breadboard/快速检查.md)（4 步 18 项，不用改程序，交互版 [`快速检查.html`](docs/breadboard/快速检查.html)），拔掉 S7 做一次回环测完整条通路，不通过时才逐段定位。要更细地查再看下面两份。
   通信有问题时看 [`docs/breadboard/通信全面检查.md`](docs/breadboard/通信全面检查.md)，从断电目视、通断、静态电压、发送和接收通路到固件逐项测，每项写了应该值和不对时的原因。交互版 [`通信全面检查.html`](docs/breadboard/通信全面检查.html) 可以填入读数自动判断。
   分级版 [`docs/breadboard/分级检查.md`](docs/breadboard/分级检查.md)（交互版 [`分级检查.html`](docs/breadboard/分级检查.html)）：先只测 MCU，再依次加上 TXB0104、241、舵机，每一级用短线做回环自测，每项写了目的。
4. **核对**：改过接线后运行 `python tools/check_wiring.py`，它会把接线清单还原成网络，再和电路图逐个网络比对（漏接、短路、插错孔、正负接反都能查出）。说明见 [`docs/breadboard/README.md`](docs/breadboard/README.md#自动核对)。

5. **两个舵机**：[`docs/两个舵机.md`](docs/两个舵机.md)。接第二个 XL330 前的调研（电流、ID、Sync Write/Read）、电源怎么改、给第二个舵机改 ID 的步骤、两个一起接上后的测试（每一步要发的 HEX 包和应该看到的结果）。包用 `python tools/dxl_packet.py` 生成，例如 `python tools/dxl_packet.py sync-goal 1:1024 2:3072`；收到的应答用 `python tools/dxl_packet.py parse "…"` 解读。

6. **爆炸图**：[`docs/exploded/xl330_exploded.html`](docs/exploded/xl330_exploded.html)。three.js 做的 3D 爆炸图：整套接线可以拆开、装回，面包板底下的金属簧片、两块转接板里的芯片、舵机内部（电机、齿轮组、控制板、磁编码器）都能单独点开看说明；“信号”可以播放 ping 包从 MCU 走到舵机、应答再走回来，同时显示 241 两个门的开关。Windows 上双击根目录的 `Start-Exploded-View.bat`：先检查 main 有没有更新（git pull），再用浏览器打开页面。页面从 CDN 加载 three.js，需要联网。

## 目录

```
docs/breadboard/   接线文档、交互页面、电路图和布局图
docs/exploded/     3D 爆炸图页面（three.js，单文件）
firmware/dxl/      驱动（dxl.c / dxl.h）、硬件接口（dxl_port.h）、测试流程（dxl_example.c，两个舵机 dxl_example2.c）
firmware/bridge/   PC ↔ 舵机转发固件（按包转发、自动切 DIR、请求队列）和要填 TODO 的模板
firmware/test/     电脑上运行的测试（驱动、转发固件）
tools/             组包和解读工具 dxl_packet.py，接线核对脚本 check_wiring.py，检查表的数据 full_check_data.py、staged_check_data.py、quick_check_data.py
```
