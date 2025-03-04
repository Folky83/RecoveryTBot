"""
Simple test script for requests-html
"""
import sys
import traceback

def test_requests_html():
    """Test if requests-html can be imported correctly"""
    try:
        print("Attempting to import requests_html...")
        from requests_html import HTMLSession
        print("Successfully imported requests_html!")
        
        print("\nCreating HTMLSession...")
        session = HTMLSession()
        print("Successfully created HTMLSession!")
        
        print("\nAttempting a simple request...")
        r = session.get("https://www.google.com")
        print(f"Request status code: {r.status_code}")
        
        print("\nAttempting to render JavaScript...")
        try:
            r.html.render(timeout=20)
            print("Successfully rendered JavaScript content!")
        except Exception as e:
            print(f"Error rendering JavaScript: {e}")
            traceback.print_exc()
            
        print("\nrequests-html is working correctly!")
        return True
    except ImportError as e:
        print(f"ImportError: {e}")
        print("\nChecking available packages...")
        try:
            import pkg_resources
            installed_packages = {pkg.key: pkg.version for pkg in pkg_resources.working_set}
            if 'requests-html' in installed_packages:
                print(f"requests-html is installed (version: {installed_packages['requests-html']})")
            else:
                print("requests-html is NOT installed")
                
            related_packages = {k: v for k, v in installed_packages.items() 
                               if 'request' in k or 'html' in k or 'pyppeteer' in k}
            print("\nRelated packages:")
            for pkg, version in related_packages.items():
                print(f"- {pkg}: {version}")
        except Exception as pkg_err:
            print(f"Error checking packages: {pkg_err}")
        
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_requests_html()