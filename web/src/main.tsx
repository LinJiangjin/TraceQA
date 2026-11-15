/**
 * 前端入口：把 App 挂载到 index.html 的 #root 节点。
 * StrictMode 只在开发模式生效，会刻意重复执行 effect 以便暴露副作用问题。
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
