# osu2arc

把 osu! 谱面转换成 **Arcaea** 的 `.aff` 谱面文件。支持两种来源：

- **osu!mania 4K** → 地面 4 轨谱面
- **osu!standard** → 全天空谱面（circle → arctap，slider → arc）

纯 Python 标准库实现，无第三方依赖。

## 用法

输入可以是 `.osu` 谱面文件，也可以直接给 `.osz` 谱面包（自动解包，转换里面的每个 `.osu`）。默认按谱面自带的 `Mode` 自动选择模式。

```bash
# 单个谱面，输出到同目录同名 .aff
python3 osu2arc.py "chart.osu"

# 指定输出文件
python3 osu2arc.py chart.osu -o out.aff

# 批量转换到目录
python3 osu2arc.py *.osu -o aff/

# 直接转 osz 谱面包
python3 osu2arc.py "941085 tieff - Our Story.osz" -o aff/

# 强制指定模式
python3 osu2arc.py chart.osu --mode sky
```

## 模式

`--mode auto`（默认）按 `[General] Mode` 判断：`3` = mania，`0` = standard。也可以用 `--mode mania` / `--mode sky` 强制。

### mania 4K

| osu!mania | Arcaea |
|---|---|
| 4 列（x 坐标换算成列号 0–3） | lane `1`–`4` |
| 普通音符 | 地面音符 `(时间,lane);` |
| 长条 note | `hold(起点,终点,lane);` |
| 时间轴（毫秒） | 直接沿用 |
| TimingPoints 的 uninherited BPM | `timing(偏移,BPM,4.00);`，多个 BPM 依次输出 |

### standard / sky

| osu!standard | Arcaea |
|---|---|
| circle | 天空点击：`arc(t,t+1,x,x,s,y,y,1,none,true)[arctap(t)];` |
| slider | `isTrace=false` 的真 arc（需要按住），按路径拆成 1–8 段，x/y 跟着曲线走 |
| slider 重复段 | 正反交替，首尾相接 |
| spinner | 丢弃（Arcaea 没有对应判定） |
| x 坐标 | `x/512` 夹到 0–1 |
| y 坐标 | `(1 - y/384) * 1.5`，即 osu 顶部最高、底部贴地 |

天空谱面没有地面音符，全部是 arc / arctap。BPM 变化同样写成多条 `timing()`。

## 已知限制

- mania 只支持 4K，其他键数直接报错
- standard 的 spinner 无法映射，会被丢掉
- slider 曲线是采样近似（Bézier / Catmull-Rom / 完美圆），每段最多 8 个 arc
- standard 没有滑条 tick 判定，slider 只保留按住判定
- 只输出谱面；难度定数、音频、曲绘、打包需要自己处理

## 许可

MIT
