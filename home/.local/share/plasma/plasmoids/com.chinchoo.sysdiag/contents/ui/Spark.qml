import QtQuick
import org.kde.kirigami as Kirigami

Canvas {
    id: spark
    property var values: []
    property real maxValue: 100
    property color lineColor: Kirigami.Theme.textColor
    property bool fill: true

    onValuesChanged: requestPaint()
    onLineColorChanged: requestPaint()
    onWidthChanged: requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const n = values.length
        if (n < 2) return
        const step = width / 59
        const x0 = width - (n - 1) * step
        const y = v => height - 1 - Math.min(1, Math.max(0, v / maxValue)) * (height - 2)

        ctx.beginPath()
        ctx.moveTo(x0, y(values[0]))
        for (let i = 1; i < n; ++i) ctx.lineTo(x0 + i * step, y(values[i]))
        ctx.strokeStyle = lineColor
        ctx.lineWidth = 1.5
        ctx.lineJoin = "round"
        ctx.stroke()

        if (fill) {
            ctx.lineTo(width, height)
            ctx.lineTo(x0, height)
            ctx.closePath()
            ctx.globalAlpha = 0.14
            ctx.fillStyle = lineColor
            ctx.fill()
        }
    }
}
