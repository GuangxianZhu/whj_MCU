# whj_MCU

KM1M7C 通过 TXB0104 和 74LVC2G241 控制 XL330 舵机的通信实验。

```
PC ──USB── KM1M7C (5V IO) ⇄ TXB0104 (5V↔3.3V) ⇄ 74LVC2G241 (TX/RX 合成 DATA) ⇄ XL330
```

## 从这里开始

1. **硬件**：[`docs/breadboard/README.md`](docs/breadboard/README.md)。电路图、面包板布局（推荐 30 列 · 400 孔，另有 17 列和 63 列）、逐根接线清单、上电前检查、物料、排查表。交互版是 [`docs/breadboard/xl330_breadboard.html`](docs/breadboard/xl330_breadboard.html)，下载后用浏览器打开，可以切换面包板尺寸、逐根打勾。
2. **软件**：[`firmware/README.md`](firmware/README.md)。DYNAMIXEL Protocol 2.0 驱动，移植到 KM1M7C 只需实现 5 个函数（DIR 引脚和 UART），附第一次通信测试流程和电脑上可跑的单元测试。

## 目录

```
docs/breadboard/   接线文档、交互页面、电路图和布局图
firmware/dxl/      驱动（dxl.c / dxl.h）、硬件接口（dxl_port.h）、测试流程（dxl_example.c）
firmware/test/     电脑上运行的驱动测试（假舵机）
```
