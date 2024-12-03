# Given an array of positive integers arr[], return the second largest element from the array. If the second largest element doesn't exist then return -1.
# Note: The second largest element should not be equal to the largest element.

#User function Template for python3
class Solution:
    def getSecondLargest(self,arr):
        arr.sort(reverse=True)
        for i in range(len(arr)-1):
            if arr[i]>arr[i+1]:
                return arr[i+1]
        return -1
                

#{ 
 # Driver Code Starts
# Initial Template for Python 3

if __name__ == "__main__":
    t = int(input())
    for _ in range(t):
        arr = list(map(int, input().split()))
        ob = Solution()
        ans = ob.getSecondLargest(arr)
        print(ans)
        print("~")
# } Driver Code Ends