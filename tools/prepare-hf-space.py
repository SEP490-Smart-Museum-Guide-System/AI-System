"""Export allowlisted quiz code for a Gradio or Docker Space; never uploads."""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def prepare(destination, sdk='docker'):
    destination = destination.expanduser().resolve()
    if destination.exists(): raise ValueError('Choose a NEW folder; existing files will not be replaced.')
    if sdk == 'gradio':
        folder=ROOT/'deploy/huggingface/gradio-quiz'
        files={name:folder/name for name in ['app.py','pytorch_engine.py','quiz_set.py','grounded_quiz.py','quiz_quality.py','requirements.txt','README.md']}
        app_files=[ROOT/'AI Chat/app'/name for name in ['__init__.py','engine.py','studio.py']]
    elif sdk == 'docker':
        files = {
            'Dockerfile': ROOT / 'deploy/huggingface/quiz/Dockerfile',
            'README.md': ROOT / 'deploy/huggingface/quiz/README.md',
            'requirements.txt': ROOT / 'AI Chat/requirements.txt',
            'tools/download_chat_model.py': ROOT / 'tools/download_chat_model.py',
        }
        app_files=sorted((ROOT/'AI Chat/app').glob('*.py'))
    else: raise ValueError('Unsupported SDK')
    for path in app_files:
        files['app/' + path.name] = path
    for relative, source in files.items():
        target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (destination / '.dockerignore').write_text('.git\n.env\n.env.*\n__pycache__\n**/__pycache__\n*.log\n', encoding='utf-8')
    print('Prepared quiz Space files:', destination)
    print('No upload performed. No .env, database, photos or local model cache copied.')
    return destination

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--sdk',choices=['docker','gradio'],default='docker')
    args = parser.parse_args(); prepare(args.destination,args.sdk)
