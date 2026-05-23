import Link from 'next/link';
import { BrainCircuit, Github, Twitter, Mail } from 'lucide-react';

const footerLinks = {
  product: [
    { label: '功能介绍', href: '#' },
    { label: '定价方案', href: '#' },
    { label: 'API 文档', href: '#' },
  ],
  resources: [
    { label: '使用指南', href: '#' },
    { label: '案例展示', href: '#' },
    { label: '常见问题', href: '#' },
  ],
  company: [
    { label: '关于我们', href: '#' },
    { label: '联系我们', href: '#' },
    { label: '加入团队', href: '#' },
  ],
  legal: [
    { label: '服务条款', href: '#' },
    { label: '隐私政策', href: '#' },
  ],
};

export function Footer() {
  return (
    <footer className="bg-brand-teal-deep text-on-dark">
      <div className="container mx-auto px-md py-section-lg">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-xl">
          {/* Brand Column */}
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-lg">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-green">
                <BrainCircuit className="h-5 w-5 text-ink" />
              </div>
              <span className="font-euclid text-heading-5 font-semibold text-on-dark">
                专利智脑
              </span>
            </Link>
            <p className="text-body-sm text-on-dark-muted mb-lg">
              AI 驱动的专利申请多智能体系统，让创新保护更专业高效。
            </p>
            <div className="flex gap-3">
              <a href="#" className="p-2 rounded-md bg-white/5 hover:bg-white/10 transition-colors">
                <Github className="w-5 h-5" />
              </a>
              <a href="#" className="p-2 rounded-md bg-white/5 hover:bg-white/10 transition-colors">
                <Twitter className="w-5 h-5" />
              </a>
              <a href="#" className="p-2 rounded-md bg-white/5 hover:bg-white/10 transition-colors">
                <Mail className="w-5 h-5" />
              </a>
            </div>
          </div>

          {/* Links Columns */}
          {Object.entries(footerLinks).map(([category, links]) => (
            <div key={category}>
              <h3 className="font-euclid text-body-sm-medium font-semibold mb-md capitalize">
                {category === 'product' ? '产品' :
                 category === 'resources' ? '资源' :
                 category === 'company' ? '公司' : '法律'}
              </h3>
              <ul className="space-y-xs">
                {links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-body-sm text-on-dark-muted hover:text-on-dark transition-colors"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-xxl pt-xl border-t border-hairline-dark flex flex-col md:flex-row justify-between items-center gap-md">
          <p className="text-body-sm text-on-dark-muted">
            © 2024 专利智脑. 保留所有权利.
          </p>
          <p className="text-body-sm text-on-dark-muted">
            Made with ❤️ for innovators
          </p>
        </div>
      </div>
    </footer>
  );
}
