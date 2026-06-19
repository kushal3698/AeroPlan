import sys
import argparse

# Reconfigure stdout and stderr to use UTF-8 to prevent encoding errors on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, FloatPrompt
from rich.markdown import Markdown
from rich.status import Status
from rich.table import Table

from agent import app, is_mock, AgentState

console = Console()

def run_cli():
    console.print(Panel.fit(
        "[bold cyan]🤖 Multi-Agent Travel Planner (LangGraph)[/bold cyan]\n"
        "Powered by LangGraph, LangChain & Rich",
        border_style="cyan"
    ))
    
    if is_mock:
        console.print("[yellow]⚠️  OPENAI_API_KEY environment variable not set. Running in SIMULATION mode.[/yellow]\n")
    else:
        console.print("[green]✅ OpenAI API Key loaded. Running in LIVE mode.[/green]\n")

    parser = argparse.ArgumentParser(description="Multi-Agent Travel Planner")
    parser.add_argument("--destination", type=str, help="Destination (e.g. 'Kyoto, Japan')")
    parser.add_argument("--days", type=int, help="Duration in days")
    parser.add_argument("--interests", type=str, help="Comma-separated interests")
    parser.add_argument("--budget", type=float, help="Budget limit")
    parser.add_argument("--currency", type=str, help="Currency (USD, EUR, JPY, GBP, INR, CAD)")
    parser.add_argument("--language", type=str, help="Language (English, Spanish, Japanese, French, German, Hindi, Telugu)")
    args = parser.parse_args()

    destination = args.destination
    duration_days = args.days
    interests_str = args.interests
    budget_limit = args.budget
    currency = args.currency
    language = args.language

    if not destination:
        destination = Prompt.ask("[bold green]✈️ Enter your destination[/bold green]", default="Kyoto, Japan")
    
    if not duration_days:
        duration_days = IntPrompt.ask("[bold green]📅 How many days?[/bold green]", default=3)
        
    if not interests_str:
        interests_str = Prompt.ask(
            "[bold green]🎨 Interests (comma-separated)[/bold green]",
            default="Historical Temples, Street Food, Nature Walks"
        )
    interests = [i.strip() for i in interests_str.split(",") if i.strip()]

    if not budget_limit:
        budget_limit = FloatPrompt.ask("[bold green]💰 Budget limit[/bold green]", default=1000.0)
        
    if not currency:
        currency = Prompt.ask("[bold green]💵 Preferred Currency (USD, EUR, JPY, GBP, INR, CAD)[/bold green]", default="USD").upper()
        
    if not language:
        language = Prompt.ask("[bold green]🗣️ Language (English, Spanish, Japanese, French, German, Hindi)[/bold green]", default="English").capitalize()

    # Prepare input state
    inputs = {
        "destination": destination,
        "duration_days": duration_days,
        "interests": interests,
        "budget_limit": budget_limit,
        "currency": currency,
        "language": language,
        "messages": []
    }

    console.print(f"\n[bold]⚙️  Initializing agent workflow graph [cyan]({language} / {currency})[/cyan]...[/bold]\n")

    current_node = None
    
    with Console().status("[bold yellow]Agent supervisor routing request...[/]") as status:
        for output in app.stream(inputs):
            for node_name, state_update in output.items():
                current_node = node_name
                
                if node_name == "researcher":
                    status.update("[bold magenta]🔍 Travel Researcher is analyzing destination and attractions...[/]")
                    import time
                    time.sleep(1)
                    
                    console.print(Panel(
                        Markdown(state_update.get("research_notes", "")),
                        title="[bold magenta]🗺️ Travel Researcher Output[/bold magenta]",
                        border_style="magenta"
                    ))
                    
                elif node_name == "budget":
                    status.update("[bold yellow]💰 Budget Agent is estimating lodging, dining, and transit...[/]")
                    import time
                    time.sleep(1)
                    
                    console.print(Panel(
                        Markdown(state_update.get("budget_notes", "")),
                        title="[bold yellow]💸 Budget Manager Output[/bold yellow]",
                        border_style="yellow"
                    ))
                    
                elif node_name == "planner":
                    status.update("[bold green]📅 Itinerary Planner is compiling the final schedule...[/]")
                    import time
                    time.sleep(1)
                    
                    console.print(Panel(
                        Markdown(state_update.get("final_itinerary", "")),
                        title="[bold green]✈️ Itinerary Planner Final Output[/bold green]",
                        border_style="green"
                    ))

    console.print("\n[bold green]🎉 Travel planning complete! Enjoy your trip to " + destination + "! [/bold green]\n")

if __name__ == "__main__":
    run_cli()
