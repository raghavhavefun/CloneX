import re
import os

def fix_run_bot():
    path = r'telegram_agent\run_bot.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace(
        "slug = email.lower().strip().replace('@', '_').replace('.', '_') if email else 'public'",
        "import re; slug = re.sub(r'[^a-z0-9._-]+', '_', email.lower().strip()) if email else 'public'"
    )
    content = content.replace(
        "slug = BOT_OWNER_EMAIL.lower().strip().replace('@', '_').replace('.', '_') if BOT_OWNER_EMAIL else 'public'",
        "import re; slug = re.sub(r'[^a-z0-9._-]+', '_', BOT_OWNER_EMAIL.lower().strip()) if BOT_OWNER_EMAIL else 'public'"
    )
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_brain():
    path = r'modules\brain.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    old_slug = """    def _owner_slug(self) -> str:
        if not self.owner_email:
            return "public"
        return self.owner_email.lower().strip().replace("@", "_").replace(".", "_")"""
        
    new_slug = """    def _owner_slug(self) -> str:
        import re
        if not self.owner_email:
            return "public"
        return re.sub(r'[^a-z0-9._-]+', '_', self.owner_email.lower().strip())"""
        
    content = content.replace(old_slug, new_slug)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_server():
    path = r'data_backend\server.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    content = content.replace(
        '''soul_path = settings.data_vault_root / owner / "Agent" / "soul.md"''',
        '''import re; slug = re.sub(r'[^a-z0-9._-]+', '_', owner.lower().strip()) if owner and owner != "global" else "global"; soul_path = settings.data_vault_root / slug / "Agent" / "soul.md"'''
    )
    content = content.replace(
        '''soul_dir = settings.data_vault_root / owner / "Agent"''',
        '''import re; slug = re.sub(r'[^a-z0-9._-]+', '_', owner.lower().strip()) if owner and owner != "global" else "global"; soul_dir = settings.data_vault_root / slug / "Agent"'''
    )
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_run_bot()
fix_brain()
fix_server()
print('Fixed slugs')
