#!/usr/bin/env python3
"""
LEGO Robotics Orchestra
-----------------------
Unified control system for EV3 and Spike Prime robots.
Projects are platform-agnostic and run on any supported hardware.

Usage:
    python main.py                          # Default: puppy flow mode
    python main.py puppy                    # Run puppy project
    python main.py puppy standup            # Run specific action
    python main.py puppy flow               # Interactive mode
    python main.py --list                   # List all projects

Structure:
    core/         - Abstract interfaces (platform-agnostic)
    platforms/    - Hardware implementations (EV3, Spike Prime)
    projects/     - Robot projects (use core/, agnostic to platform)
"""

import sys
import os
import importlib.util

# Root directory
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)


def load_project_module(project: str):
    """Load a project module from projects/project/project.py"""
    project_dir = os.path.join(ROOT_DIR, "projects", project)
    project_file = os.path.join(project_dir, f"{project}.py")
    
    if not os.path.exists(project_file):
        return None, None
    
    # Change to project directory for config
    os.chdir(project_dir)
    
    # Load module
    spec = importlib.util.spec_from_file_location(project, project_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    return module, project_dir


def run_project(project: str, action: str = "flow"):
    """Run a robot project."""
    module, project_dir = load_project_module(project)
    
    if module is None:
        print(f"Project not found: projects/{project}")
        return
    
    # Get RemotePuppy, RemoteController, or similar class
    remote = None
    for cls_name in ['RemotePuppy', 'RemoteController', 'Controller', 'Robot']:
        if hasattr(module, cls_name):
            remote = getattr(module, cls_name)()
            break
    
    if remote is None:
        print(f"No controller class found in {project}")
        return
    
    if action == "flow":
        remote.flow()
    else:
        result = remote.execute_action(action)
        if not result.get("success") and "error" in result:
            print("Error:", result["error"])
    
    remote.disconnect()


# Project registry: name -> platform hint (for display only)
PROJECTS = {
    "puppy": "ev3",  # Platform hint (project is still agnostic)
}


def list_projects():
    """List all available projects."""
    print("Available projects:")
    print()
    for name, platform in PROJECTS.items():
        print(f"  {name:15} [current: {platform}]")
    print()
    print("Structure:")
    print("  core/         Abstract robot interfaces")
    print("  platforms/    EV3, Spike Prime implementations")
    print("  projects/     Robot projects (platform-agnostic)")


def main():
    args = sys.argv[1:]
    
    # Default
    project = "puppy"
    action = "flow"
    
    if len(args) >= 1:
        if args[0] in ("--help", "-h"):
            print(__doc__)
            list_projects()
            return
        if args[0] in ("--list", "-l"):
            list_projects()
            return
        project = args[0]
    
    if len(args) >= 2:
        action = args[1]
    
    if project not in PROJECTS:
        print(f"Unknown project: {project}")
        list_projects()
        return
    
    print(f"Running {project}...")
    run_project(project, action)


if __name__ == "__main__":
    main()

