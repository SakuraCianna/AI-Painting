import { Component, type ErrorInfo, type ReactNode } from "react";

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  hasError: boolean;
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("AI Painting UI error", error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <main className="workspace error-workspace">
          <section className="error-boundary" role="alert">
            <p className="panel-label">界面错误</p>
            <strong>画布界面加载失败</strong>
            <span>请刷新页面或重新启动前后端服务。</span>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}
