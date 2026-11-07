#!/usr/bin/env python3
"""Record local episode feedback separately from objective verification. No network calls."""
import argparse
import json
import os
from pathlib import Path
import tempfile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--task-success-user', required=True, choices=['success', 'partial', 'failed', 'unknown'])
    parser.add_argument('--useful', required=True, choices=['yes', 'no', 'unknown'])
    parser.add_argument('--comment', default='')
    parser.add_argument('--correction', action='append', default=[])
    parser.add_argument('--objective-success', choices=['yes', 'no', 'unknown'])
    parser.add_argument('--objective-evidence', action='append', default=[])
    parser.add_argument('--allow-training', choices=['yes', 'no'])
    parser.add_argument('--reviewed', action='store_true', help='A human has reviewed the episode, not merely the final answer')
    args = parser.parse_args(argv)
    root = args.archive.expanduser().resolve()
    if any((p/'.git').exists() for p in [root, *root.parents]):
        parser.error('Labels belong in the private archive, outside Git')
    path = root/'labels.json'
    if not path.is_file() or not (root/'export.json').is_file():
        parser.error('Expected an existing export archive with labels.json and export.json')
    if args.objective_success in ('yes', 'no') and not args.objective_evidence:
        parser.error('An objective result requires at least one --objective-evidence reference')
    labels = json.loads(path.read_text(encoding='utf-8'))
    tri = {'yes': True, 'no': False, 'unknown': None}
    labels.update(task_success_user=args.task_success_user, useful=tri[args.useful],
                  comment=args.comment, human_corrections=args.correction,
                  reviewed=args.reviewed, include_for_training=False)
    if args.objective_success is not None:
        labels.update(objective_success=tri[args.objective_success], objective_evidence=args.objective_evidence)
    if args.allow_training is not None:
        labels['allow_training'] = args.allow_training == 'yes'
    os.umask(0o077)
    with tempfile.NamedTemporaryFile('w', dir=root, prefix='.labels-', suffix='.json', delete=False, encoding='utf-8') as tmp:
        tmp.write(json.dumps(labels, ensure_ascii=False, indent=2) + '\n')
        temporary = Path(tmp.name)
    temporary.replace(path)
    print(json.dumps({'saved': str(path), 'task_success_user': args.task_success_user,
                      'reviewed': args.reviewed, 'include_for_training': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
