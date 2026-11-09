# frozen_string_literal: true

# ==============================================================================
# Step 1: Verify Simulated AWS FastMCP Server & Cloud Armor Edge WAF Policy
# ==============================================================================
def step_1_mcp_cloud_armor_check(handles:, maximum_score:, resources:)
  ret_hash = {
    done: false,
    score: 0,
    message: 'error_message',
    student_message: 'error_message'
  }

  begin
    logging = handles['project_0.LoggingV2'] || handles[:LoggingV2]
    compute = handles['project_0.ComputeV1'] || handles[:ComputeV1]
    storage = handles['project_0.StorageV1'] || handles[:StorageV1]
    project_id = (resources['project_0']['project_id'] rescue nil) ||
                 (resources[:project_0][:project_id] rescue nil) ||
                 (logging.project rescue nil) ||
                 (storage.project rescue nil)

    verified = false

    if compute && project_id
      begin
        policies = compute.list_security_policies(project_id)&.items || []
        verified = true if policies.any? { |p| p.name.to_s.include?('cymbal-mcp-edge-waf-policy') }
      rescue StandardError
        # Fallback to LoggingV2 / StorageV1 below
      end
    end

    if !verified && logging && project_id
      begin
        lab_start_time = Time.at(Time.now.to_i - 14_400).utc.iso8601
        custom_filter = [
          "timestamp>\"#{lab_start_time}\"",
          '(protoPayload.serviceName="compute.googleapis.com" OR protoPayload.serviceName="run.googleapis.com")',
          '(protoPayload.methodName:"securityPolicies" OR protoPayload.resourceName:"cymbal-mcp-edge-waf-policy" OR protoPayload.resourceName:"cymbal-aws-mcp-sim")'
        ].join(' AND ')

        request = Google::Apis::LoggingV2::ListLogEntriesRequest.new
        request.resource_names = ["projects/#{project_id}"]
        request.filter = custom_filter

        entries = logging.list_entry_log_entries(request)&.entries || []
        verified = true if entries.count.positive?
      rescue StandardError
        # Fallback to StorageV1 below
      end
    end

    if !verified && storage && project_id
      begin
        bucket_name = "#{project_id}-ge-agw-state"
        objects = storage.list_objects(bucket_name)&.items || []
        object_names = objects.map(&:name)
        verified = true if object_names.any? { |name| name.include?('step1_mock_mcp_and_cloud_armor.json') }
      rescue StandardError
        # Ignore fallback error
      end
    end

    if verified
      ret_hash = {
        done: true,
        score: maximum_score,
        message: 'success',
        student_message: 'success'
      }
    end
  rescue StandardError => e
    ret_hash[:message] = e.message
    ret_hash[:student_message] = 'error_message'
  end

  ret_hash
end
