# osu2arc

把 **osu!mania 4K** 谱面转换成 **Arcaea** 的 `.aff` 谱面文件。

纯 Python 标准库实现，无第三方依赖。

## 用法

```bash
# 单个谱面，输出到同目录同名 .aff
python3 osu2arc.py "Saikoro - far in the blue sky... (1nar) [42].osu"

# 指定输出文件
python3 osu2arc.py chart.osu -o out.aff

# 批量转换到目录
python3 osu2arc.py *.osu -o aff/
```

## 转换规则

| osu!mania | Arcaea |
|---|---|
| 4 列（x 坐标换算成列号 0–3） | lane `1`–`4` |
| 普通音符（type bit 0） | 地面音符 `(时间,lane);` |
| 长条 note（type bit 128） | `hold(起点,终点,lane);` |
| 时间轴（毫秒） | 直接沿用，不缩放 |
| TimingPoints 里的 uninherited BPM | `timing(偏移,BPM,4.00);`，多个 BPM 变化会依次输出 |

输出文件结构：

```
AudioOffset:0
-
timing(0,148.00,4.00);
(3243,1);
(3445,4);
hold(3680,5555,2);
```

## 已知限制

- 只支持 4K，遇到其他键数会直接报错。
- osu 没有天空判定线概念，转换结果只有地面点击和长条，**没有 Arcaea 的 arc（音弧）**。
- 同帧同 lane 的重复音符会被去重。
- 谱面难度、定数、曲绘、音频需要自己处理，工具只产出 `.aff`。
- 判定线以外的位置（osu 列宽之外）会被夹到最近的合法 lane。

## 许可

MIT
