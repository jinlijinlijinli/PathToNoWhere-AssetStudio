using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
namespace PtnChunkSupport
{
    public static class Live2DIntegration
    {
        public static void Install(Form form)
        {
            var menu = form.MainMenuStrip;
            if (menu == null) return;
            foreach (ToolStripItem existing in menu.Items) if (existing.Name == "ptnLive2DMenu") return;
            var root = new ToolStripMenuItem("Live2D 工具") { Name = "ptnLive2DMenu" };
            var process = new ToolStripMenuItem("无期迷途 Live2D 一键提取与处理…");
            process.Click += (sender, args) =>
            {
                var executable = Path.Combine(AppContext.BaseDirectory, "Live2DTools", "无期迷途Live2D提取工具.exe");
                if (!File.Exists(executable)) executable = Path.Combine(AppContext.BaseDirectory, "Live2DTools", "无期迷途Live2D处理工具.exe");
                if (!File.Exists(executable))
                {
                    MessageBox.Show(form, "未找到 Live2DTools 组件，请保留完整的工具目录。", "Live2D 工具", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                try { Process.Start(new ProcessStartInfo(executable) { UseShellExecute = true, WorkingDirectory = Path.GetDirectoryName(executable) }); }
                catch (Exception e) { MessageBox.Show(form, e.Message, "Live2D 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error); }
            };
            root.DropDownItems.Add(process); menu.Items.Add(root);
        }
    }
}
